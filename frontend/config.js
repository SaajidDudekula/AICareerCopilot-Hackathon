// Frontend configuration — NON-SECRET values only.
//
// This file is loaded by the browser and is fully visible to anyone who
// views page source. Never put real secrets here (API keys, JWT signing
// secrets, database credentials, etc.) — those belong only in the
// backend's .env file, which never gets sent to the browser.
//
// Google's OAuth Client ID is intentionally public/shareable by design —
// Google's own docs confirm it's safe to embed in frontend code. It is
// NOT the same as a Client Secret (which we don't use in this app at all).

const CONFIG = {
  API_BASE: "http://localhost:8000",
  GOOGLE_CLIENT_ID: "570908060205-etigpsmp34pci5tg12qheboh8pgihd6a.apps.googleusercontent.com",
};
