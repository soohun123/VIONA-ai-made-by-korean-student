"""Read GGUF metadata before allocating model/context memory."""
import struct
from pathlib import Path

def read_metadata(path):
    with Path(path).open('rb') as f:
        def read(n):
            b=f.read(n)
            if len(b)!=n: raise ValueError('Truncated GGUF')
            return b
        def u32(): return struct.unpack('<I',read(4))[0]
        def u64(): return struct.unpack('<Q',read(8))[0]
        def string(keep=True):
            n=u64()
            if n>64*1024*1024: raise ValueError('Invalid string')
            if keep: return read(n).decode('utf-8')
            f.seek(n,1)
        formats={0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
        def value(t,keep=True):
            if t==8: return string(keep)
            if t==9:
                subtype,count=u32(),u64()
                if count>10000000: raise ValueError('Invalid array')
                for _ in range(count): value(subtype,False)
                return {'array_type':subtype,'length':count} if keep else None
            if t not in formats: raise ValueError('Unknown GGUF type')
            fmt='<'+formats[t]
            return struct.unpack(fmt,read(struct.calcsize(fmt)))[0]
        if read(4)!=b'GGUF': raise ValueError('Not GGUF')
        version=u32()
        if version not in (2,3): raise ValueError('Unsupported GGUF version')
        tensors,count=u64(),u64()
        if count>100000: raise ValueError('Invalid metadata count')
        result={'gguf_version':version,'tensor_count':tensors}
        for _ in range(count):
            key=string()
            result[key]=value(u32())
        return result
