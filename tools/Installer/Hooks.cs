// Wires RevivalMod.dll into the game:
//   Bootstrap.InitialiseShell()        -> RevivalMod.Entry.Init()            (banner)
//   LocalizationService.GetText(key)   -> RevivalMod.Entry.Text(key) ?? original   (funny loading texts)
using System;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

static class Hooks
{
    public static void Inject(ModuleDefinition mod, string revivalModPath)
    {
        var rm = ModuleDefinition.ReadModule(new System.IO.MemoryStream(System.IO.File.ReadAllBytes(revivalModPath)));
        var entry = rm.GetType("RevivalMod.Entry");
        var init = mod.ImportReference(entry.Methods.First(m => m.Name == "Init"));
        var text = mod.ImportReference(entry.Methods.First(m => m.Name == "Text"));

        var boot = mod.GetType("GameStateMachine.Bootstrap").Methods.First(m => m.Name == "InitialiseShell");
        var il = boot.Body.GetILProcessor();
        il.InsertBefore(boot.Body.Instructions[0], il.Create(OpCodes.Call, init));

        var getText = mod.GetType("Services.LocalizationService").Methods
            .First(m => m.Name == "GetText" && m.Parameters.Count == 1 && m.Parameters[0].ParameterType.FullName == "System.String");
        il = getText.Body.GetILProcessor();
        var first = getText.Body.Instructions[0];
        // var s = Entry.Text(key); if (s != null) return s;
        il.InsertBefore(first, il.Create(OpCodes.Ldarg_1));
        il.InsertBefore(first, il.Create(OpCodes.Call, text));
        il.InsertBefore(first, il.Create(OpCodes.Dup));
        il.InsertBefore(first, il.Create(OpCodes.Brfalse, first));   // leaves the dup'd null on the stack -> pop below
        il.InsertBefore(first, il.Create(OpCodes.Ret));
        var pop = il.Create(OpCodes.Pop);
        il.InsertBefore(first, pop);
        // retarget: the brfalse must land on the pop, not on the original first instruction
        var br = getText.Body.Instructions.First(i => i.OpCode == OpCodes.Brfalse && i.Operand == first);
        br.Operand = pop;
        Console.WriteLine("  hooks: Bootstrap.InitialiseShell -> Entry.Init, LocalizationService.GetText -> Entry.Text");
    }
}
