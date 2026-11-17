using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Linq;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using Microsoft.Win32;

class Updater {
    const string PublicKey = "__PUBLIC_KEY_XML_BASE64__";
    static JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 8000000 };
    static string Hash(Stream stream) { using(var sha=SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant(); }
    static string HashFile(string p) { using(var f=File.OpenRead(p)) return Hash(f); }
    static Dictionary<string,object> Obj(object x) { return (Dictionary<string,object>)x; }
    static string Str(Dictionary<string,object> x,string key) { return Convert.ToString(x[key]); }
    static void Write(string path,object value) { Directory.CreateDirectory(Path.GetDirectoryName(path)); string temp=path+"."+Guid.NewGuid()+".tmp";File.WriteAllText(temp,Json.Serialize(value),new UTF8Encoding(false));if(File.Exists(path))File.Delete(path);File.Move(temp,path); }
    static string Under(string root,string relative) {
        if(String.IsNullOrEmpty(relative)||Path.IsPathRooted(relative)||relative.Contains(":")||relative.Contains("\\")||relative.Split('/').Any(x=>x==".."||x=="."||x==""))throw new Exception("Unsafe update path");
        if(relative!="NOVERA_AI_Desktop.exe"&&relative!="NOVERA_Update.exe"&&relative!="app-version.json"&&!relative.StartsWith("_internal/",StringComparison.Ordinal))throw new Exception("User data/model paths cannot be updated");
        string lower=relative.ToLowerInvariant();
        if(new[]{".gguf",".safetensors",".pt",".pth",".bin"}.Any(x=>lower.EndsWith(x))||lower.Split('/').Any(x=>x==".secrets"||x=="model-pack"||x=="accounts"||x=="exports"))throw new Exception("Models and private user files are excluded");
        string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
        if(!full.StartsWith(Path.GetFullPath(root).TrimEnd('\\')+"\\",StringComparison.OrdinalIgnoreCase))throw new Exception("Path escaped installation");
        string parent=Path.GetDirectoryName(full);
        while(parent!=null&&parent.Length>=Path.GetFullPath(root).TrimEnd('\\').Length){if(Directory.Exists(parent)&&(File.GetAttributes(parent)&FileAttributes.ReparsePoint)!=0)throw new Exception("Reparse point in update path");parent=Path.GetDirectoryName(parent);}
        return full;
    }
    static Dictionary<string,object> ReadManifest(string feed) {
        var envelope=Obj(Json.DeserializeObject(File.ReadAllText(feed,Encoding.UTF8)));
        byte[] body=Convert.FromBase64String(Str(envelope,"payload")),signature=Convert.FromBase64String(Str(envelope,"signature"));
        using(var rsa=new RSACryptoServiceProvider()){rsa.PersistKeyInCsp=false;rsa.FromXmlString(Encoding.UTF8.GetString(Convert.FromBase64String(PublicKey)));if(!rsa.VerifyData(body,CryptoConfig.MapNameToOID("SHA256"),signature))throw new Exception("Update signature is invalid");}
        var m=Obj(Json.DeserializeObject(Encoding.UTF8.GetString(body)));
        if(Str(m,"app_id")!="NOVERA_AI_Desktop"||Convert.ToInt32(m["schema"])!=1)throw new Exception("Wrong update application/schema");
        return m;
    }
    static string Current(string app) { return Str(Obj(Json.DeserializeObject(File.ReadAllText(Path.Combine(app,"app-version.json")))),"version"); }
    static bool Newer(string a,string b) { return new Version(a)>new Version(b); }
    static IEnumerable<Dictionary<string,object>> Files(Dictionary<string,object> m) { return ((object[])m["files"]).Select(Obj); }
    static void NoOtherInstance(string app,int parent) {
        string target=Path.GetFullPath(Path.Combine(app,"NOVERA_AI_Desktop.exe"));
        foreach(var p in Process.GetProcessesByName("NOVERA_AI_Desktop")){
            if(p.Id==parent)continue;
            try {if(String.Equals(p.MainModule.FileName,target,StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Another NOVERA process is still running; update postponed");}
            catch(InvalidOperationException){throw;}catch(System.ComponentModel.Win32Exception){}
        }
    }
    static int Main(string[] args) {
        if(args.Length<4)return 2;
        string mode=args[0],feed=Path.GetFullPath(args[1]),app=Path.GetFullPath(args[2]),result=Path.GetFullPath(args[3]);
        bool smoke=args.Contains("--smoke-restart"),restart=args.Contains("--restart");
        string backup=null,attemptedVersion=null;var changed=new List<string>();var existed=new HashSet<string>();bool committed=false;
        try {
            var manifest=ReadManifest(feed);string current=Current(app),version=Str(manifest,"version");attemptedVersion=version;
            bool available=Newer(version,current)&&((object[])manifest["supported_versions"]).Any(x=>Convert.ToString(x)==current);
            if(mode=="--check"){Write(result,new {ok=true,available=available,current_version=current,version=version,reason=Newer(version,current)&&!available?"unsupported_base":""});return 0;}
            if(mode!="--apply"||!available)throw new Exception("Update does not match this installed version");
            int parent=Int32.Parse(args[4]);
            try {var process=Process.GetProcessById(parent);if(!process.WaitForExit(60000))throw new Exception("Application has not exited; no files changed");}catch(ArgumentException){}
            string lockName;using(var ms=new MemoryStream(Encoding.UTF8.GetBytes(app.ToUpperInvariant())))lockName=Hash(ms).Substring(0,24);
            using(var mutex=new Mutex(false,"Local\\NOVERAUpdate-"+lockName)){
                if(!mutex.WaitOne(0))throw new Exception("Another update is in progress");
                try {
                    NoOtherInstance(app,-1);
                    string payloadName=Str(manifest,"package");
                    if(payloadName!=Path.GetFileName(payloadName)||payloadName.Contains(":")||!payloadName.EndsWith(".zip"))throw new Exception("Invalid payload name");
                    string package=Path.Combine(Path.GetDirectoryName(feed),payloadName);
                    // Keep the archive locked against replacement throughout validation/apply.
                    using(var input=new FileStream(package,FileMode.Open,FileAccess.Read,FileShare.Read)){
                        if(Hash(input)!=Str(manifest,"sha256"))throw new Exception("Update package checksum mismatch");input.Position=0;
                        var files=Files(manifest).ToList();
                        if(!files.Any(x=>Str(x,"path")=="app-version.json"))throw new Exception("Missing version commit file");
                        long total=files.Sum(x=>Convert.ToInt64(x["size"]));
                        if(total>2147483648L||total<1)throw new Exception("Invalid update size");
                        string work=Path.Combine(Path.GetDirectoryName(result),"transactions",Guid.NewGuid().ToString("N"));
                        string stage=Path.Combine(work,"stage");backup=Path.Combine(work,"backup");Directory.CreateDirectory(stage);Directory.CreateDirectory(backup);
                        if(new DriveInfo(Path.GetPathRoot(work)).AvailableFreeSpace<total*2+134217728L||new DriveInfo(Path.GetPathRoot(app)).AvailableFreeSpace<total+134217728L)throw new Exception("Not enough free disk space");
                        using(var zip=new ZipArchive(input,ZipArchiveMode.Read,true)){
                            var expected=new HashSet<string>(files.Select(x=>Str(x,"path")),StringComparer.OrdinalIgnoreCase);
                            if(expected.Count!=files.Count||zip.Entries.Count!=files.Count)throw new Exception("Duplicate or extra archive entries");
                            foreach(var entry in zip.Entries){
                                if(!expected.Remove(entry.FullName))throw new Exception("Unexpected archive entry");
                                var item=files.First(x=>Str(x,"path")==entry.FullName);string destination=Under(app,entry.FullName);
                                if(File.Exists(destination)&&(File.GetAttributes(destination)&FileAttributes.ReparsePoint)!=0)throw new Exception("Reparse file target");
                                object before;var beforeMap=Obj(item["before"]);if(!beforeMap.TryGetValue(current,out before))throw new Exception("Unknown base version");
                                if(before==null){if(File.Exists(destination))throw new Exception("New file would overwrite a user file");}
                                else if(!File.Exists(destination)||HashFile(destination)!=Convert.ToString(before))throw new Exception("Existing app file differs; update aborted safely");
                                if(entry.Length!=Convert.ToInt64(item["size"]))throw new Exception("Wrong entry size");
                                string staged=Under(stage,entry.FullName);Directory.CreateDirectory(Path.GetDirectoryName(staged));
                                using(var source=entry.Open())using(var output=new FileStream(staged,FileMode.CreateNew)){byte[] buffer=new byte[1048576];long n=0;int read;while((read=source.Read(buffer,0,buffer.Length))>0){n+=read;if(n>entry.Length)throw new Exception("Archive limit exceeded");output.Write(buffer,0,read);}}
                                if(HashFile(staged)!=Str(item,"sha256"))throw new Exception("Extracted file checksum mismatch");
                            }
                            if(expected.Count!=0)throw new Exception("Missing update entries");
                        }
                        // Back up all originals before the first write. Commit version last.
                        foreach(var item in files){string relative=Str(item,"path"),target=Under(app,relative);if(File.Exists(target)){string saved=Under(backup,relative);Directory.CreateDirectory(Path.GetDirectoryName(saved));File.Copy(target,saved,false);existed.Add(relative);}}
                        foreach(var item in files.OrderBy(x=>Str(x,"path")=="app-version.json"?1:0)){
                            string relative=Str(item,"path"),target=Under(app,relative);Directory.CreateDirectory(Path.GetDirectoryName(target));changed.Add(relative);File.Copy(Under(stage,relative),target,true);
                            if(HashFile(target)!=Str(item,"sha256"))throw new Exception("Installed file verification failed");
                        }
                        if(Current(app)!=version)throw new Exception("Version commit mismatch");committed=true;
                        try {
                            using(var registry=Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\{302881F9-B378-4E7B-8597-E594C5721210}_is1",true)){
                                if(registry!=null&&String.Equals(Convert.ToString(registry.GetValue("InstallLocation")).TrimEnd('\\'),app.TrimEnd('\\'),StringComparison.OrdinalIgnoreCase)){
                                    registry.SetValue("DisplayVersion",version);registry.SetValue("DisplayName","NOVERA AI Desktop");
                                }
                            }
                        }catch{}
                        Write(result,new {ok=true,status="applied",version=version,backup=backup,files=files.Count});
                    }
                } finally {mutex.ReleaseMutex();}
            }
            if(restart)Process.Start(new ProcessStartInfo(Path.Combine(app,"NOVERA_AI_Desktop.exe"),smoke?"--gui-smoke":""){WorkingDirectory=app,UseShellExecute=false});
            return 0;
        } catch(Exception error) {
            var rollbackErrors=new List<string>();
            if(!committed&&backup!=null)foreach(string relative in changed.AsEnumerable().Reverse()){
                try {string target=Under(app,relative);if(existed.Contains(relative)){string saved=Under(backup,relative);if(!File.Exists(target)||HashFile(target)!=HashFile(saved))File.Copy(saved,target,true);}else if(File.Exists(target))File.Delete(target);}catch(Exception e){rollbackErrors.Add(e.Message);}
            }
            Write(result,new {ok=false,status="failed",version=attemptedVersion,error=error.Message,rollback_ok=rollbackErrors.Count==0,rollback_errors=rollbackErrors});
            if(restart&&rollbackErrors.Count==0)try{Process.Start(new ProcessStartInfo(Path.Combine(app,"NOVERA_AI_Desktop.exe"),smoke?"--gui-smoke":""){WorkingDirectory=app,UseShellExecute=false});}catch{}
            return 1;
        }
    }
}
