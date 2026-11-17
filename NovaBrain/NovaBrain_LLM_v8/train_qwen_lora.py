"""Bounded, offline Qwen LoRA teaching on CPU. Does not activate the result."""
import argparse
import datetime
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

import psutil
from runtime_settings import read_settings
from text_training_runtime import LEASE, active_training

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--corpus',type=Path)
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--fast-cpu',action='store_true')
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    if not 30 <= args.seconds <= 900:
        parser.error('Training budget must be 30..900 seconds')
    if active_training():
        raise RuntimeError('Another verified trainer is active')
    if psutil.virtual_memory().available < 6 * 2**30:
        raise RuntimeError('6 GiB available RAM required before loading trainer')
    run = ROOT / 'data/text-training/runs' / uuid.uuid4().hex
    run.mkdir(parents=True)
    process = psutil.Process()
    lease = {'id': run.name, 'pid': os.getpid(), 'process_created': process.create_time(), 'state': 'running'}
    LEASE.write_text(json.dumps(lease), encoding='utf-8')
    report = {'id': run.name, 'state': 'loading', 'budget_seconds': args.seconds,
              'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'device': 'cpu', 'cpu_threads': read_settings()['cpu_threads'],
              'dtype': 'bfloat16 base; float32 adapters', 'steps': [], 'seen_ids': [],
              'base': 'Qwen/Qwen2.5-Coder-1.5B-Instruct',
              'base_revision': '2e1fd397ee46e1388853d2af2c993145b0f1098a',
              'human_eval_used': False, 'activated': False}
    done = threading.Event()

    def save():
        temporary = run / 'report.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(20):
            try:
                temporary.replace(run / 'report.json')
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.05)

    def monitor():
        with (run / 'resources.jsonl').open('a', encoding='utf-8') as handle:
            while not done.is_set():
                memory = psutil.virtual_memory()
                sample = {'time': time.time(), 'rss_gib': process.memory_info().rss / 2**30,
                          'system_used_gib': memory.used / 2**30, 'available_gib': memory.available / 2**30}
                handle.write(json.dumps(sample) + '\n'); handle.flush()
                if memory.used >= 13.5 * 2**30 or memory.available < 2.5 * 2**30:
                    (run / 'resource-stop.json').write_text(json.dumps(sample), encoding='utf-8')
                    # Stop only this trainer immediately; unvalidated weights remain inactive.
                    os._exit(88)
                done.wait(.5)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        threads = report['cpu_threads']
        os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                          OMP_NUM_THREADS=str(threads), OPENBLAS_NUM_THREADS=str(threads))
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import LoraConfig, get_peft_model,PeftModel
        from peft.utils import get_peft_model_state_dict
        torch.set_num_threads(threads); torch.set_num_interop_threads(1); torch.manual_seed(42)
        base = ROOT / 'models/training/qwen-coder-1.5b'
        corpus_file = args.corpus.resolve() if args.corpus else ROOT / 'data/text-training/teaching-corpus-v1.jsonl'
        if not corpus_file.is_relative_to(ROOT):raise ValueError('Teaching corpus outside installation')
        report['corpus_sha256'] = hashlib.sha256(corpus_file.read_bytes()).hexdigest()
        tokenizer = AutoTokenizer.from_pretrained(base, local_files_only=True, trust_remote_code=False)
        corpus = [json.loads(line) for line in corpus_file.read_text(encoding='utf-8').splitlines()]
        examples = []
        for record in corpus:
            messages = [{'role': 'system', 'content': '한국어 질문에 직접 답하세요. 코드는 요청한 함수와 조건을 지키세요.'}] + record['messages']
            prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
            tokens = tokenizer.apply_chat_template(messages, tokenize=True)
            if len(tokens) > (384 if args.fast_cpu else 192) or tokens[:len(prefix)] != prefix or len(tokens) <= len(prefix):
                report.setdefault('skipped_examples', []).append({'id': record['id'], 'tokens': len(tokens)})
                continue
            examples.append((record['id'], tokens, len(prefix)))
        if not examples:
            raise RuntimeError('No complete supervised examples fit sequence limit')
        report['examples'] = len(examples)
        report['max_sequence_length'] = max(len(tokens) for _, tokens, _ in examples)
        model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.bfloat16,
                local_files_only=True, trust_remote_code=False, low_cpu_mem_usage=True,
                attn_implementation='eager')
        layers = model.config.num_hidden_layers
        report['train_layers'] = list(range(layers - 4, layers))
        if args.resume:
            if not args.resume.resolve().is_relative_to(ROOT):raise ValueError('Adapter outside installation')
            model=PeftModel.from_pretrained(model,args.resume,local_files_only=True,is_trainable=True)
            report['resume_adapter']=str(args.resume)
        else:model = get_peft_model(model, LoraConfig(r=2, lora_alpha=4, lora_dropout=0,
                    target_modules=['q_proj', 'v_proj'], layers_to_transform=report['train_layers'],
                    task_type='CAUSAL_LM', bias='none'))
        model.config.use_cache = False
        if args.fast_cpu:
            backbone=model.get_base_model()
            backbone.model.embed_tokens.float();backbone.model.norm.float();backbone.lm_head.float()
            for block in backbone.model.layers[-4:]:block.float()
            def before_frozen(block,inputs):block.float()
            def after_frozen(block,inputs,output):
                hidden=output[0] if isinstance(output,tuple) else output
                if hidden.requires_grad:raise RuntimeError('Frozen prefix unexpectedly requires gradients')
                block.bfloat16()
                return output
            for block in backbone.model.layers[:-4]:
                if any(p.requires_grad for p in block.parameters()):raise RuntimeError('Trainable layer in frozen prefix')
                block.register_forward_pre_hook(before_frozen);block.register_forward_hook(after_frozen)
            report['cpu_mode']='BF16 storage for frozen prefix, temporary FP32 compute; FP32 train layers'
        else:model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
        model.train()
        parameters = [p for p in model.parameters() if p.requires_grad]
        report['trainable_parameters'] = sum(p.numel() for p in parameters)
        optimizer = torch.optim.AdamW(parameters, lr=3e-5, weight_decay=0)

        def digest():
            h = hashlib.sha256()
            for name, value in sorted(get_peft_model_state_dict(model).items()):
                h.update(name.encode()); h.update(value.detach().float().cpu().numpy().tobytes())
            return h.hexdigest()

        report['initial_adapter_hash'] = digest()
        report['state'] = 'training'; save()
        started = time.monotonic()
        index = 0
        while time.monotonic() - started < args.seconds:
            if args.once and index>=len(examples):break
            if report['steps'] and args.seconds-(time.monotonic()-started)<report['steps'][-1]['seconds']*1.25:
                report['budget_stop_reason']='Next estimated step would exceed the remaining time budget'
                break
            identifier, tokens, prefix_length = examples[index % len(examples)]
            inputs = torch.tensor([tokens], dtype=torch.long)
            labels = inputs.clone(); labels[:, :prefix_length] = -100
            optimizer.zero_grad(set_to_none=True)
            step_start = time.monotonic()
            output = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=labels)
            loss = output.loss
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            loss.backward(); torch.nn.utils.clip_grad_norm_(parameters, 1.0); optimizer.step()
            report['steps'].append({'step': index + 1, 'id': identifier, 'loss': float(loss.detach()),
                                    'seconds': time.monotonic() - step_start})
            if identifier not in report['seen_ids']:
                report['seen_ids'].append(identifier)
            report['training_seconds'] = time.monotonic() - started
            save()
            print('STEP', index + 1, identifier, round(float(loss.detach()), 5), flush=True)
            del output, loss, inputs, labels
            index += 1
        if not report['steps']:
            raise RuntimeError('No optimizer steps completed')
        report['final_adapter_hash'] = digest()
        if report['initial_adapter_hash'] == report['final_adapter_hash']:
            raise RuntimeError('Training did not change adapter weights')
        model.save_pretrained(run / 'adapter', safe_serialization=True)
        report['state'] = 'trained'
        report['optimizer_steps'] = len(report['steps'])
        report['completed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
        print('TRAINED_RUN', run, flush=True)
    except Exception as exc:
        report.update(state='error', error=type(exc).__name__ + ': ' + str(exc)); save()
        raise
    finally:
        done.set(); thread.join(timeout=2)
        lease['state'] = report['state']
        LEASE.write_text(json.dumps(lease), encoding='utf-8')


if __name__ == '__main__':
    main()
