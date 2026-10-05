import { api, session } from "./api.js";
import { app, go, logout, register, setUser } from "./app.js";
import { loadAssets } from "./assets.js";
import { setAuthFailureHandler } from "./socket.js";

import mountLogin from "./screens/login.js";
import mountHome from "./screens/home.js";
import { mountStandardRooms, mountRumbleRooms } from "./screens/rooms.js";
import mountWaiting from "./screens/waiting.js";
import mountGame from "./screens/game.js";
import mountAiDifficulty from "./screens/ai_difficulty.js";
import mountAiGame from "./screens/ai_game.js";
import mountLeaderboard from "./screens/leaderboard.js";
import mountProfile from "./screens/profile.js";
import mountAugmentSelect from "./screens/augment_select.js";
import mountRumbleGame from "./screens/rumble_game.js";

register("login", mountLogin);
register("home", mountHome);
register("rooms", mountStandardRooms);
register("rumble_rooms", mountRumbleRooms);
register("waiting", mountWaiting);
register("game", mountGame);
register("ai_difficulty", mountAiDifficulty);
register("ai_game", mountAiGame);
register("leaderboard", mountLeaderboard);
register("profile", mountProfile);
register("augment_select", mountAugmentSelect);
register("rumble_game", mountRumbleGame);

setAuthFailureHandler(() => {
  if (app.user) logout("Session expirée, veuillez vous reconnecter");
});

async function boot() {
  const root = document.getElementById("app");
  root.textContent = "Chargement…";
  root.className = "boot";
  await loadAssets();

  // "Rester connecté": validate the saved token before trusting it.
  if (session.load()) {
    try {
      const me = await api.me();
      setUser(me);
      go("home");
      return;
    } catch (err) {
      if (err.status === 401) session.clear();
    }
  }
  go("login");
}

boot();
