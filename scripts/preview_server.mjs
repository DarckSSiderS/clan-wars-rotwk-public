import http from "node:http";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const distDir = path.join(rootDir, "frontend", "dist");
const publicDir = path.join(rootDir, "frontend", "public");
const port = Number(process.env.PORT || 8000);

const token = "preview-admin-token";
const adminUser = {
  id: 1,
  username: "admin",
  email: "admin@example.com",
  is_active: true,
  balance: 1000,
  level: 10,
  experience: 32000,
  avatar_url: null,
  language: "ru",
  allow_clan_invites: true,
  role: {
    id: 1,
    name: "admin",
    description: "Администратор системы",
  },
};

const territories = [
  {
    id: 1,
    name: "Форд Изена",
    region: "Рохан",
    description: "Нейтральная территория для проверки клановых войн",
    svg_path_data: "",
    owner_clan_id: null,
    resource_wealth: 4,
    strategic_value: 8,
    population: 0,
    fortifications: 1,
    trade_routes: [],
    special_resources: [],
    climate: "temperate",
    terrain: "plains",
    status: "neutral",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 2,
    name: "Минас Тирит",
    region: "Гондор",
    description: "Занятая территория для проверки атаки владельца",
    svg_path_data: "",
    owner_clan_id: 2,
    resource_wealth: 9,
    strategic_value: 10,
    population: 12000,
    fortifications: 9,
    trade_routes: [],
    special_resources: ["stone"],
    climate: "temperate",
    terrain: "city",
    status: "active",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const sampleClan = {
  id: 1,
  name: "Preview Clan",
  description: "Клан для локальной проверки",
  leader_id: adminUser.id,
  avatar_url: null,
  level: 1,
  experience: 0,
  max_members: 20,
  created_at: new Date().toISOString(),
};

const shopItems = [
  {
    id: 1,
    name: "Красная рамка",
    description: "Тестовый предмет профиля",
    price: 100,
    item_type: "profile_frame",
    rarity: "rare",
    image_url: null,
    css_class: "profile-frame-gold",
    slot: "profile_frame",
    category: "profile_frame",
    is_available: true,
    created_at: new Date().toISOString(),
  },
];

let inventory = [];
let balance = adminUser.balance;

function sendJson(res, status, data) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(data));
}

function sendError(res, status, detail) {
  sendJson(res, status, { detail });
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function parseBody(req) {
  const body = await readBody(req);
  const contentType = req.headers["content-type"] || "";
  if (contentType.includes("application/x-www-form-urlencoded")) {
    return Object.fromEntries(new URLSearchParams(body));
  }
  if (contentType.includes("application/json") && body) {
    return JSON.parse(body);
  }
  return {};
}

function isAuthorized(req) {
  return req.headers.authorization === `Bearer ${token}`;
}

async function handleApi(req, res, url) {
  const route = url.pathname.replace(/^\/api\/v1/, "");

  if (req.method === "POST" && route === "/auth/token") {
    const body = await parseBody(req);
    if (body.username === "admin" && body.password === "admin") {
      sendJson(res, 200, { access_token: token, token_type: "bearer" });
      return;
    }
    sendError(res, 401, "Неверное имя пользователя или пароль");
    return;
  }

  if (req.method === "POST" && route === "/auth/register") {
    sendJson(res, 200, adminUser);
    return;
  }

  if (route.startsWith("/localization/webpage/") && route.endsWith("/texts")) {
    sendJson(res, 200, { texts: {} });
    return;
  }

  if (route.startsWith("/localization/text/")) {
    const identifier = decodeURIComponent(route.split("/").pop() || "");
    sendJson(res, 200, { text: identifier });
    return;
  }

  if (!isAuthorized(req) && route !== "/statistics/overall") {
    sendError(res, 401, "Preview API: войдите как admin/admin");
    return;
  }

  if (req.method === "GET" && route === "/users/me") {
    sendJson(res, 200, { ...adminUser, balance });
    return;
  }

  if (req.method === "GET" && route === "/users/profile/admin") {
    sendJson(res, 200, { ...adminUser, balance });
    return;
  }

  if (req.method === "PUT" && /^\/users\/\d+$/.test(route)) {
    const body = await parseBody(req);
    Object.assign(adminUser, body);
    sendJson(res, 200, { ...adminUser, balance });
    return;
  }

  if (req.method === "PUT" && /^\/users\/\d+\/balance$/.test(route)) {
    const body = await parseBody(req);
    balance += Number(body.amount || 0);
    sendJson(res, 200, { ...adminUser, balance });
    return;
  }

  if (req.method === "GET" && /^\/users\/\d+\/clan$/.test(route)) {
    sendJson(res, 200, sampleClan);
    return;
  }

  if (req.method === "GET" && route === "/clans/my") {
    sendJson(res, 200, { ...sampleClan, members: [{ id: 1, user_id: 1, clan_id: 1, rank: "Лидер", user: adminUser }] });
    return;
  }

  if (req.method === "GET" && route === "/clans/invites/") {
    sendJson(res, 200, []);
    return;
  }

  if (req.method === "GET" && route === "/territories/") {
    sendJson(res, 200, territories);
    return;
  }

  if (req.method === "GET" && route === "/territories/stats") {
    sendJson(res, 200, { total: territories.length, neutral: 1, active: 1, contested: 0 });
    return;
  }

  if (req.method === "GET" && route.startsWith("/territories/")) {
    const territory = territories.find((item) => route.includes(String(item.id))) || territories[0];
    sendJson(res, 200, territory);
    return;
  }

  if (req.method === "GET" && route === "/wars/active/") {
    sendJson(res, 200, [
      {
        id: 1,
        territory_id: 1,
        territory_name: "Форд Изена",
        attacking_clan_id: 1,
        attacking_clan_name: sampleClan.name,
        defending_clan_id: null,
        defending_clan_name: null,
        winner_clan_id: null,
        winner_clan_name: null,
        war_type: "neutral_capture",
        status: "active",
        required_wins: 25,
        started_at: new Date().toISOString(),
        ends_at: null,
        ended_at: null,
        clan_scores: [{ clan_id: 1, clan_name: sampleClan.name, wins: 7, losses: 2, active_participants: 1 }],
        progress_percent: 28,
      },
    ]);
    return;
  }

  if (req.method === "GET" && route.startsWith("/wars/clan/")) {
    sendJson(res, 200, []);
    return;
  }

  if (req.method === "POST" && route === "/wars/") {
    const body = await parseBody(req);
    sendJson(res, 200, {
      id: Date.now(),
      territory_id: body.territory_id,
      territory_name: territories.find((item) => item.id === Number(body.territory_id))?.name || "Территория",
      attacking_clan_id: 1,
      attacking_clan_name: sampleClan.name,
      defending_clan_id: null,
      defending_clan_name: null,
      winner_clan_id: null,
      winner_clan_name: null,
      war_type: "neutral_capture",
      status: "active",
      required_wins: 25,
      started_at: new Date().toISOString(),
      ends_at: null,
      ended_at: null,
      clan_scores: [{ clan_id: 1, clan_name: sampleClan.name, wins: 0, losses: 0, active_participants: 1 }],
      progress_percent: 0,
    });
    return;
  }

  if (req.method === "GET" && route === "/shop/items/available/") {
    const ownedItemIds = new Set(inventory.map((item) => item.item_id));
    sendJson(res, 200, shopItems.filter((item) => !ownedItemIds.has(item.id)));
    return;
  }

  if (req.method === "GET" && /^\/shop\/users\/\d+\/items\/?$/.test(route)) {
    sendJson(res, 200, inventory);
    return;
  }

  if (req.method === "POST" && route === "/shop/purchase/") {
    const body = await parseBody(req);
    const item = shopItems.find((entry) => entry.id === Number(body.item_id));
    if (!item) {
      sendError(res, 404, "Предмет не найден");
      return;
    }
    if (inventory.some((entry) => entry.item_id === item.id)) {
      sendError(res, 400, "Предмет уже куплен");
      return;
    }
    if (balance < item.price) {
      sendError(res, 400, "Недостаточно средств");
      return;
    }
    balance -= item.price;
    const userItem = {
      id: Date.now(),
      user_id: 1,
      item_id: item.id,
      purchased_at: new Date().toISOString(),
      is_equipped: false,
      item,
    };
    inventory.push(userItem);
    sendJson(res, 200, { user_item: userItem, new_balance: balance, item_price: item.price });
    return;
  }

  if (req.method === "POST" && route === "/shop/equip/") {
    const body = await parseBody(req);
    const userItem = inventory.find((entry) => entry.id === Number(body.user_item_id));
    if (userItem) {
      userItem.is_equipped = true;
    }
    sendJson(res, 200, userItem || {});
    return;
  }

  if (req.method === "POST" && route.startsWith("/shop/unequip/")) {
    const userItemId = Number(route.split("/").pop());
    const userItem = inventory.find((entry) => entry.id === userItemId);
    if (userItem) {
      userItem.is_equipped = false;
    }
    sendJson(res, 200, userItem || {});
    return;
  }

  if (req.method === "GET" && route.startsWith("/achievements/users/")) {
    sendJson(res, 200, []);
    return;
  }

  if (req.method === "GET" && route === "/statistics/overall") {
    sendJson(res, 200, { total_matches: 0, total_players: 1, total_clans: 1, total_wars: 1 });
    return;
  }

  if (req.method === "GET" && route.startsWith("/statistics/")) {
    sendJson(res, 200, []);
    return;
  }

  sendJson(res, 200, Array.isArray(url.searchParams.get("list")) ? [] : {});
}

async function fileExists(filePath) {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile();
  } catch {
    return false;
  }
}

function contentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
  }[ext] || "application/octet-stream";
}

async function serveStatic(req, res, url) {
  let requestPath = decodeURIComponent(url.pathname);
  if (requestPath === "/") {
    requestPath = "/index.html";
  }

  const candidates = [
    path.resolve(distDir, `.${requestPath}`),
    path.resolve(publicDir, `.${requestPath}`),
  ].filter((candidate) => candidate.startsWith(distDir) || candidate.startsWith(publicDir));

  let filePath = null;
  for (const candidate of candidates) {
    if (await fileExists(candidate)) {
      filePath = candidate;
      break;
    }
  }

  if (!filePath) {
    filePath = path.join(distDir, "index.html");
  }

  const data = await fs.readFile(filePath);
  res.writeHead(200, { "Content-Type": contentType(filePath) });
  res.end(data);
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
      });
      res.end();
      return;
    }

    if (url.pathname.startsWith("/api/v1")) {
      await handleApi(req, res, url);
      return;
    }

    await serveStatic(req, res, url);
  } catch (error) {
    console.error(error);
    sendError(res, 500, "Preview server error");
  }
});

server.listen(port, "0.0.0.0", () => {
  console.log(`Preview server: http://localhost:${port}/`);
  console.log("Login: admin / admin");
});
