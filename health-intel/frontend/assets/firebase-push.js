const FIREBASE_CONFIG = window.PCUBE_FIREBASE_CONFIG || {};
const FIREBASE_VAPID_KEY = String(window.PCUBE_FIREBASE_VAPID_KEY || "").trim();
const FIREBASE_APP_URL = "/firebase-messaging-sw.js";

function hasFirebaseConfig() {
  return Boolean(
    FIREBASE_CONFIG &&
      FIREBASE_CONFIG.apiKey &&
      FIREBASE_CONFIG.authDomain &&
      FIREBASE_CONFIG.projectId &&
      FIREBASE_CONFIG.messagingSenderId &&
      FIREBASE_CONFIG.appId,
  );
}

async function getFirebaseModules() {
  const [appMod, messagingMod] = await Promise.all([
    import("https://www.gstatic.com/firebasejs/10.13.2/firebase-app.js"),
    import("https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging.js"),
  ]);
  return { appMod, messagingMod };
}

async function ensureServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    throw new Error("This browser does not support service workers.");
  }
  return navigator.serviceWorker.register(FIREBASE_APP_URL, { scope: "/" });
}

async function requestBrowserPermission() {
  if (!("Notification" in window)) {
    throw new Error("This browser does not support notifications.");
  }
  if (Notification.permission === "granted") return "granted";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Push notification permission was not granted.");
  }
  return permission;
}

async function getBrowserPushToken() {
  if (!hasFirebaseConfig()) {
    throw new Error("Firebase web config is missing.");
  }
  if (!FIREBASE_VAPID_KEY) {
    throw new Error("Firebase VAPID key is missing.");
  }

  await requestBrowserPermission();
  const { appMod, messagingMod } = await getFirebaseModules();
  const firebaseApp = appMod.getApps().length
    ? appMod.getApp()
    : appMod.initializeApp(FIREBASE_CONFIG);
  const messaging = messagingMod.getMessaging(firebaseApp);
  const registration = await ensureServiceWorker();
  const token = await messagingMod.getToken(messaging, {
    vapidKey: FIREBASE_VAPID_KEY,
    serviceWorkerRegistration: registration,
  });
  if (!token) {
    throw new Error("Firebase did not return a push token.");
  }
  return token;
}

window.PCubeFirebasePush = {
  getBrowserPushToken,
  hasFirebaseConfig,
};
