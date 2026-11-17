"""Offline WASI CPython. No inherited sockets/env; read-only stdlib only.

Generated code never executes in host Python. Every run has a fresh store,
256 MiB linear-memory ceiling, epoch timeout, and bounded captured output.
"""
import json, threading
from pathlib import Path
import wasmtime

ROOT=Path(__file__).resolve().parent

class Sandbox:
    def __init__(self):
        config=wasmtime.Config()
        config.epoch_interruption=True
        self.engine=wasmtime.Engine(config)
        self.module=wasmtime.Module.from_file(self.engine,str(ROOT/'sandbox/bin/python-3.11.4.wasm'))
        self.linker=wasmtime.Linker(self.engine)
        self.linker.define_wasi()

    def run(self,code,timeout=10):
        store=wasmtime.Store(self.engine)
        store.set_limits(memory_size=256*1024*1024,instances=1,memories=1)
        store.set_epoch_deadline(1)
        wasi=wasmtime.WasiConfig()
        wasi.argv=['python','-I','-B','-c',code]
        wasi.env=[('PYTHONHASHSEED','0')]
        wasi.preopen_dir(str(ROOT/'sandbox/usr'),'/usr',False)
        output=[]
        def capture(data):
            if sum(map(len,output))+len(data)>65536:raise RuntimeError('Output limit')
            output.append(bytes(data))
            return len(data)
        wasi.stdout_custom=capture
        wasi.stderr_custom=capture
        store.set_wasi(wasi)
        timer=threading.Timer(timeout,self.engine.increment_epoch)
        timer.daemon=True
        timer.start()
        error=None
        try:
            instance=self.linker.instantiate(store,self.module)
            instance.exports(store)['_start'](store)
            passed=True
        except wasmtime.ExitTrap as exc:
            passed=exc.code==0
            if not passed:error=str(exc)
        except Exception as exc:
            passed=False;error=str(exc)
        finally:
            timer.cancel()
            store.close()
        return {'passed':passed,'output':b''.join(output).decode('utf-8',errors='replace'),'error':error}

if __name__=='__main__':
    s=Sandbox()
    print(json.dumps(s.run("import sys; print(sys.version); print('SANDBOX_OK')")))
    print(json.dumps(s.run("import socket; socket.socket().connect(('1.1.1.1',443))")))
    print(json.dumps(s.run("open('/usr/local/lib/probe-write','w').write('x')")))
    print(json.dumps(s.run("open('/etc/passwd').read()")))
    print(json.dumps(s.run('while True: pass',1)))
