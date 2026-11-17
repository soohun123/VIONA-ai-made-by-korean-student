"""Process-local NVIDIA DLL discovery; no system PATH or driver changes."""
import os,sys,ctypes
from pathlib import Path
_directories=[]
_libraries=[]
def initialize_cuda():
    if os.name!='nt':return
    site=Path(sys.prefix)/'Lib/site-packages/nvidia'
    for name in ('cuda_runtime','cublas'):
        folder=site/name/'bin'
        if folder.is_dir():_directories.append(os.add_dll_directory(str(folder)))
    for package,name in [('cuda_runtime','cudart64_12.dll'),('cublas','cublasLt64_12.dll'),('cublas','cublas64_12.dll')]:
        path=site/package/'bin'/name
        if path.is_file():_libraries.append(ctypes.CDLL(str(path)))
