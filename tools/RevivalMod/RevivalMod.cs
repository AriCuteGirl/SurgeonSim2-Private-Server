// In-game bits of the Surgeon Simulator 2 revival: the "PRIVATE SERVER BY ARI" banner
// and silly loading / matchmaking texts. The patcher wires Entry.Init() into Bootstrap.InitialiseShell
// and Entry.Text(key) in front of LocalizationService.GetText(key).
using UnityEngine;

namespace RevivalMod
{
    public static class Entry
    {
        static bool _started;

        public static void Init()
        {
            if (_started) return;
            _started = true;
            var go = new GameObject("RevivalBanner");
            Object.DontDestroyOnLoad(go);
            go.AddComponent<Banner>();
        }

        static readonly string[] Loading =
        {
            "Cracking femboys",
            "Patting good kitty",
            "Loading infinite nukes",
            "Bribing Bob with snacks",
            "Sharpening the spoons",
            "Untangling the intestines",
            "Hiding the spare kidneys",
            "Feeding the server hamster",
            "Teaching Bob to wash hands",
            "Defrosting the fridge organs",
            "Petting the server puppy",
            "Reviving dead servers (ironic)",
        };

        static readonly string[] Finding =
        {
            "Sniffing out\nsurgeons",
            "Calling\nthe femboys",
            "Shaking the\ntreat bag",
            "Summoning\nyour bestie",
        };

        static readonly string[] Searching =
        {
            "Searching under the operating table",
            "Asking Bob",
            "Checking the vents",
        };

        // Returns a replacement for a localisation key, or null to keep the game's text.
        public static string Text(string key)
        {
            string[] pool;
            switch (key)
            {
                case "LOADING": pool = Loading; break;
                case "FINDING_PLAYER": pool = Finding; break;
                case "FRIENDS_SEARCH_SEARCHING": pool = Searching; break;
                default: return null;
            }
            // changes every 2.5 s so long loads cycle through the jokes
            int i = (int)(Time.realtimeSinceStartup / 2.5f) % pool.Length;
            return pool[i];
        }
    }

    public class Banner : MonoBehaviour
    {
        const string Label = "PRIVATE SERVER BY ARI";
        GUIStyle _style;

        void OnGUI()
        {
            GUI.depth = -1000;
            if (_style == null)
            {
                _style = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.UpperCenter, fontStyle = FontStyle.Bold };
            }
            int size = Mathf.Max(14, Screen.height / 34);
            _style.fontSize = size;
            var rect = new Rect(0, size * 0.4f, Screen.width, size * 2);
            _style.normal.textColor = new Color(0f, 0f, 0f, 0.75f);
            GUI.Label(new Rect(rect.x + 2, rect.y + 2, rect.width, rect.height), Label, _style);
            _style.normal.textColor = new Color(1f, 0.42f, 0.71f, 1f);
            GUI.Label(rect, Label, _style);
        }
    }
}
