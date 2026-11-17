"""Release request-scoped native samplers without waiting for Python cycle GC.

llama-cpp-python 0.3.36 generate replaces _sampler, while LlamaSampler's
ExitStack callback captures itself. Its native allocation otherwise survives
until cyclic GC. Keep the loaded model, mmap and KV context intact.
"""
def release_generation(llm,chunks=None):
    try:
        if chunks is not None:chunks.close()
    finally:
        sampler=getattr(llm,'_sampler',None)
        if sampler is not None:
            try:sampler.close()
            finally:llm._sampler=None
