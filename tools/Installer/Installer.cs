// SS2 Revival installer: turns an untouched Surgeon Simulator 2 1.5.1.561 folder into a
// private-server copy (patched Assembly-CSharp.dll + RevivalMod.dll + PupBerg Steam emulator).
// Nothing from the game is shipped: the user's own DLL is patched in place, originals are kept.
//
//   SS2Revival-Installer                          interactive (double-click), uses the folder it sits in
//   SS2Revival-Installer install [gameDir] [--host H] [--port P] [--name N] [--room R] [--pupberg-lobby H:P] [--yes]
//   SS2Revival-Installer uninstall [gameDir]
//   SS2Revival-Installer patch <in.dll> <out.dll> <host> [port] [RevivalMod.dll]    (dev)
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

static class Installer
{
    // No server address is built in: it comes from server.txt next to the installer
    // (host=..., port=..., pupberg_lobby=...), --host, or the user types it in.
    const string DefaultPort = "8090";
    const string DefaultRoom = "SS2-REVIVAL";
    const string AppId = "774791";
    const string ExeName = "Surgeon Simulator 2.exe";
    const string DataDir = "Surgeon Simulator 2_Data";

    static string Here => AppContext.BaseDirectory;

    static int Main(string[] args)
    {
        bool interactive = args.Length == 0;
        try
        {
            if (args.Length > 0 && args[0] == "patch")
            {
                Patch.Run(args[1], args[2], args[3], args.Length > 4 ? args[4] : DefaultPort,
                    args.Length > 5 ? args[5] : Path.Combine(Here, "RevivalMod.dll"));
                return 0;
            }
            var opts = ParseOptions(args.Skip(args.Length > 0 ? 1 : 0).ToArray(), out var positional);
            string cmd = args.Length > 0 ? args[0] : "install";
            string gameDir = FindGame(positional.FirstOrDefault(), interactive);
            if (cmd == "uninstall") Uninstall(gameDir);
            else if (cmd == "install") Install(gameDir, opts, !opts.ContainsKey("yes"));
            else throw new Exception("unknown command " + cmd);
            if (interactive) Pause();
            return 0;
        }
        catch (Exception e)
        {
            Console.ForegroundColor = ConsoleColor.Red;
            Console.WriteLine("\nERROR: " + e.Message);
            Console.ResetColor();
            if (interactive) Pause();
            return 1;
        }
    }

    static Dictionary<string, string> ParseOptions(string[] args, out List<string> positional)
    {
        var o = new Dictionary<string, string>();
        positional = new List<string>();
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--yes") o["yes"] = "1";
            else if (args[i].StartsWith("--") && i + 1 < args.Length) o[args[i].Substring(2)] = args[++i];
            else positional.Add(args[i]);
        }
        return o;
    }

    static string FindGame(string given, bool interactive)
    {
        foreach (var d in new[] { given, Here, Directory.GetCurrentDirectory(), Path.GetDirectoryName(Here.TrimEnd('/', '\\')) })
            if (!string.IsNullOrEmpty(d) && File.Exists(Path.Combine(d, ExeName))) return Path.GetFullPath(d);
        if (interactive)
        {
            Console.WriteLine("Drag your old Surgeon Simulator 2 folder (the one with \"Surgeon Simulator 2.exe\") here and press Enter:");
            var d = (Console.ReadLine() ?? "").Trim().Trim('"', '\'');
            if (File.Exists(Path.Combine(d, ExeName))) return Path.GetFullPath(d);
        }
        throw new Exception("Surgeon Simulator 2 folder not found. Put the installer files inside the game folder and run it again.");
    }

    static string Ask(string question, string def, bool interactive)
    {
        if (!interactive) return def;
        Console.Write($"{question} [{def}]: ");
        var a = (Console.ReadLine() ?? "").Trim();
        return a.Length > 0 ? a : def;
    }

    static void Install(string game, Dictionary<string, string> o, bool interactive)
    {
        Console.ForegroundColor = ConsoleColor.Magenta;
        Console.WriteLine("=== Surgeon Simulator 2 - PRIVATE SERVER BY ARI ===");
        Console.ResetColor();
        Console.WriteLine("Game folder: " + game);

        string managed = Path.Combine(game, DataDir, "Managed");
        string plugins = Path.Combine(game, DataDir, "Plugins", "x86_64");
        string dll = Path.Combine(managed, "Assembly-CSharp.dll");
        string dllOrig = dll + ".original";
        string steamApi = Path.Combine(plugins, "steam_api64.dll");
        string steamApiOrig = steamApi + ".valve_original";
        string settings = Path.Combine(plugins, "steam_settings");
        string userIni = Path.Combine(settings, "configs.user.ini");

        var version = File.Exists(Path.Combine(game, "BuildVersion.txt"))
            ? File.ReadAllText(Path.Combine(game, "BuildVersion.txt")).Replace("\0", "").Trim() : "?";
        Console.WriteLine("Build: " + version + (version.Contains("1.5.1") ? " (ok, last co-op build)" : " (WARNING: expected 1.5.1.561)"));

        // keep the settings from an earlier install as defaults
        string oldName = null, oldId = null;
        if (File.Exists(userIni))
            foreach (var line in File.ReadAllLines(userIni))
            {
                if (line.StartsWith("account_name=")) oldName = line.Substring(13);
                if (line.StartsWith("account_steamid=")) oldId = line.Substring(16);
            }

        var cfg = ReadServerTxt();
        string host = o.GetValueOrDefault("host") ?? cfg.GetValueOrDefault("host");
        if (string.IsNullOrEmpty(host)) host = Ask("Server address (IP or hostname of the SS2 server)", "", interactive);
        if (string.IsNullOrWhiteSpace(host)) throw new Exception("no server address: pass --host <ip> or put host=<ip> in server.txt");
        string port = o.GetValueOrDefault("port") ?? cfg.GetValueOrDefault("port") ?? DefaultPort;
        string lobby = o.GetValueOrDefault("pupberg-lobby") ?? cfg.GetValueOrDefault("pupberg_lobby");
        string name = o.GetValueOrDefault("name");
        string pickedId = null;
        if (name == null)
        {
            // like PupBerg's account picker: offer the Steam accounts that logged in on this PC
            var accounts = SteamAccounts();
            if (interactive && accounts.Count > 0)
            {
                Console.WriteLine("\nWho are you? (your Steam accounts on this PC)");
                for (int i = 0; i < accounts.Count; i++) Console.WriteLine($"  {i + 1}) {accounts[i].name}  ({accounts[i].id})");
                Console.WriteLine($"  {accounts.Count + 1}) type a different name");
                var a = Ask("Pick a number", "1", true);
                if (int.TryParse(a, out var n) && n >= 1 && n <= accounts.Count)
                {
                    name = accounts[n - 1].name;
                    pickedId = accounts[n - 1].id;
                }
            }
            name ??= Ask("Your name in game", oldName ?? Environment.UserName, interactive);
        }
        string room = o.GetValueOrDefault("room") ?? Ask("PupBerg room code (same for you and your friends)", DefaultRoom, interactive);

        // 1. back up originals once
        if (!File.Exists(dllOrig)) File.Copy(dll, dllOrig);
        if (File.Exists(steamApi) && !File.Exists(steamApiOrig)) File.Copy(steamApi, steamApiOrig);

        // 2. patch from the untouched original
        Console.WriteLine("\nPatching Assembly-CSharp.dll ...");
        File.Copy(Path.Combine(Here, "RevivalMod.dll"), Path.Combine(managed, "RevivalMod.dll"), true);
        Patch.Run(dllOrig, dll, host, port, Path.Combine(managed, "RevivalMod.dll"));

        // 3. PupBerg (Steam emulator) so no Steam login / ownership check is needed
        Console.WriteLine("Installing PupBerg ...");
        File.Copy(Path.Combine(Here, "pupberg", "steam_api64.dll"), steamApi, true);
        Directory.CreateDirectory(settings);
        File.WriteAllText(Path.Combine(settings, "steam_appid.txt"), AppId);
        File.WriteAllText(Path.Combine(game, "steam_appid.txt"), AppId);
        string steamId = pickedId ?? oldId ?? (76561198000000000UL + (ulong)new Random().Next(10_000_000, 999_999_999)).ToString();
        File.WriteAllText(userIni,
            "[user::general]\n" +
            $"account_name={name}\n" +
            $"account_steamid={steamId}\n" +
            "language=english\n");
        File.WriteAllText(Path.Combine(settings, "configs.overlay.ini"),
            "[overlay::general]\n" +
            "enable_experimental_overlay=1\n" +
            "\n[overlay::pupberg]\n" +
            "theme=Pink Neon\n" +
            "network_mode=server\n" +
            (string.IsNullOrEmpty(lobby) ? "" : $"lobby_server={lobby}\n") +
            $"lobby_room={room}\n" +
            "lobby_public=0\n" +
            "lobby_auto_join=1\n");

        Console.ForegroundColor = ConsoleColor.Green;
        Console.WriteLine($"\nDone! Server {host}:{port}, PupBerg room {room}, you are \"{name}\".");
        Console.ResetColor();
        Console.WriteLine("Start the game with \"Surgeon Simulator 2.exe\" (Steam does not need to be running).");
        Console.WriteLine("In the lobby: walk to the terminal / party menu and invite your friend, or join them from the PupBerg overlay (Shift+Tab).");
        Console.WriteLine("To undo everything run:  SS2Revival-Installer uninstall");
    }

    // Steam's config/loginusers.vdf: "7656119..." { "AccountName" ".." "PersonaName" ".." ... }
    static List<(string id, string name)> SteamAccounts()
    {
        var list = new List<(string, string)>();
        var roots = new List<string>();
        if (OperatingSystem.IsWindows())
        {
            try
            {
                using var k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam");
                if (k?.GetValue("SteamPath") is string sp) roots.Add(sp);
            }
            catch { }
            roots.Add(@"C:\Program Files (x86)\Steam");
        }
        else
        {
            var home = Environment.GetEnvironmentVariable("HOME") ?? "";
            roots.Add(Path.Combine(home, ".local/share/Steam"));
            roots.Add(Path.Combine(home, ".steam/steam"));
            roots.Add(Path.Combine(home, ".var/app/com.valvesoftware.Steam/data/Steam"));
        }
        foreach (var r in roots)
        {
            var f = Path.Combine(r, "config", "loginusers.vdf");
            if (!File.Exists(f)) continue;
            var text = File.ReadAllText(f);
            foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(text, "\"(7656\\d{13})\"\\s*\\{([^}]*)\\}"))
            {
                var persona = System.Text.RegularExpressions.Regex.Match(m.Groups[2].Value, "\"PersonaName\"\\s*\"([^\"]*)\"");
                var name = persona.Success && persona.Groups[1].Value.Length > 0 ? persona.Groups[1].Value : "Steam user";
                if (!list.Exists(x => x.Item1 == m.Groups[1].Value)) list.Add((m.Groups[1].Value, name));
            }
            if (list.Count > 0) break;
        }
        return list;
    }

    static Dictionary<string, string> ReadServerTxt()
    {
        var d = new Dictionary<string, string>();
        var f = Path.Combine(Here, "server.txt");
        if (File.Exists(f))
            foreach (var line in File.ReadAllLines(f))
            {
                var i = line.IndexOf('=');
                if (i > 0 && !line.TrimStart().StartsWith("#")) d[line.Substring(0, i).Trim()] = line.Substring(i + 1).Trim();
            }
        return d;
    }

    static void Uninstall(string game)
    {
        string managed = Path.Combine(game, DataDir, "Managed");
        string plugins = Path.Combine(game, DataDir, "Plugins", "x86_64");
        void Restore(string f, string backup)
        {
            if (File.Exists(backup)) { File.Copy(backup, f, true); File.Delete(backup); Console.WriteLine("restored " + Path.GetFileName(f)); }
        }
        Restore(Path.Combine(managed, "Assembly-CSharp.dll"), Path.Combine(managed, "Assembly-CSharp.dll.original"));
        Restore(Path.Combine(plugins, "steam_api64.dll"), Path.Combine(plugins, "steam_api64.dll.valve_original"));
        foreach (var f in new[] { Path.Combine(managed, "RevivalMod.dll"), Path.Combine(game, "steam_appid.txt") })
            if (File.Exists(f)) File.Delete(f);
        Console.WriteLine("Uninstalled (steam_settings folder kept so your PupBerg identity survives a reinstall).");
    }

    static void Pause()
    {
        Console.WriteLine("\nPress Enter to close.");
        Console.ReadLine();
    }
}
