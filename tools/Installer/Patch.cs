// Points Surgeon Simulator 2 (v1.5.1.561, the last co-op build) at a revival server and hooks in RevivalMod.dll.
using System;
using System.Collections.Generic;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class Patch
{
    public static void Run(string input, string output, string host, string port, string revivalMod)
    {
        string web = host + ":" + port;

        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(input)));
        var asm = AssemblyDefinition.ReadAssembly(input, new ReaderParameters { AssemblyResolver = resolver, InMemory = true, ReadingMode = ReadingMode.Immediate });
        var mod = asm.MainModule;

        // Exact string literal replacements (Prod environment only).
        var strings = new Dictionary<string, string>
        {
            ["nat.ss2.bsprd.uk"] = host,                       // STUN 8021 / TURN 8022 / notifications 8023 (UDP)
            ["ss2.bsprd.uk"] = web,                            // REST API
            ["mm-status.ss2.bsprd.uk"] = web,                  // /version /status /scheduledTimes
            ["https://ss2.bsprd.uk/auth/healthcheck"] = "http://" + web + "/auth/healthcheck",
            ["https://ss2-json.bossastudios.com/Production/"] = "http://" + web + "/news/",
        };
        var hits = new Dictionary<string, int>();

        foreach (var type in mod.GetTypes())
        foreach (var method in type.Methods.Where(m => m.HasBody))
        {
            bool isHttps = type.FullName == "Services.CrappyHttpsRequestService";
            foreach (var ins in method.Body.Instructions)
            {
                if (ins.OpCode != OpCodes.Ldstr) continue;
                var s = (string)ins.Operand;
                if (strings.TryGetValue(s, out var repl))
                {
                    ins.Operand = repl;
                    hits[s] = hits.GetValueOrDefault(s) + 1;
                }
                else if (isHttps && s == "https://")
                {
                    ins.Operand = "http://";
                    hits[s] = hits.GetValueOrDefault(s) + 1;
                }
            }
        }

        foreach (var kv in hits) Console.WriteLine($"  {kv.Value}x  {kv.Key}");
        var missing = strings.Keys.Append("https://").Where(k => !hits.ContainsKey(k)).ToList();
        if (missing.Count > 0)
        {
            Console.Error.WriteLine("not found: " + string.Join(", ", missing));
            throw new Exception("this is not the 1.5.1.561 Assembly-CSharp.dll (missing: " + string.Join(", ", missing) + ")");
        }
        Hooks.Inject(mod, revivalMod);
        asm.Write(output);
        Console.WriteLine($"patched -> {output} (server {web})");
    }
}
