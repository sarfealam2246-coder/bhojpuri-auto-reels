import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import type {
  ApiVault,
  FacebookPageSlot,
  PhotoPostItem,
  ReelHistoryItem,
  ResearchChannel,
  ScheduleConfig,
} from '../types/studio';

const DB_NAME = 'bhojpuri_reelstudio_db';
const DB_VERSION = 1;
const STORE_KV = 'kv_store';
const STORE_REELS = 'reels_history';
const STORE_PHOTOS = 'photo_posts';

export const DEFAULT_VAULT: ApiVault = {
  githubPat: '',
  githubRepo: 'sarfealam2246-coder/bhojpuri-auto-reels',
  groqApiKey: '',
  geminiApiKey: '',
  cloudflareAccountId: '',
  cloudflareApiToken: '',
};

export const DEFAULT_SCHEDULE: ScheduleConfig = {
  morningReelIst: '09:00',
  eveningReelIst: '19:00',
  photoPostEnabled: true,
  photoPostDays: ['Tue', 'Thu', 'Sun'],
  photoPostIst: '13:00',
  autoSaveToDevice: true,
};

export const DEFAULT_CHANNELS: ResearchChannel[] = [
  { id: 'ch_1', name: 'Bhojpuri Rangdari Dialogue', youtubeHandleOrUrl: 'bhojpuri rangdari attitude dialogue shorts', category: 'rangdari', enabled: true },
  { id: 'ch_2', name: 'Bhojpuri Bewafai Sad Shayari', youtubeHandleOrUrl: 'bhojpuri bewafai sad dialogue status shorts', category: 'bewafai', enabled: true },
  { id: 'ch_3', name: 'Desi Bhojpuri Comedy Viral', youtubeHandleOrUrl: 'bhojpuri desi comedy funny dialogue shorts', category: 'comedy', enabled: true },
  { id: 'ch_4', name: 'Bhojpuri Judai Emotional', youtubeHandleOrUrl: 'bhojpuri judai emotional sad dialogue shorts', category: 'judai', enabled: true },
  { id: 'ch_5', name: 'Gaon Vafadari & Imandari', youtubeHandleOrUrl: 'bhojpuri imandari vafadari emotional story shorts', category: 'vafadari', enabled: true },
  { id: 'ch_6', name: 'Purvanchal Dabang Attitude', youtubeHandleOrUrl: 'purvanchal bhojpuri dabang dialogue shorts', category: 'rangdari', enabled: true },
  { id: 'ch_7', name: 'Bihar UP Desi Punch', youtubeHandleOrUrl: 'bihar up desi comedy viral dialogue shorts', category: 'comedy', enabled: true },
  { id: 'ch_8', name: 'Broken Heart Bhojpuri', youtubeHandleOrUrl: 'bhojpuri tutal dil bewafai shayari shorts', category: 'bewafai', enabled: true },
  { id: 'ch_9', name: 'Yari Dosti Bhojpuri Status', youtubeHandleOrUrl: 'bhojpuri yaari dosti vafadari dialogue shorts', category: 'vafadari', enabled: true },
  { id: 'ch_10', name: 'Maa Baap Emotional Bhojpuri', youtubeHandleOrUrl: 'bhojpuri maa baap emotional dialogue shorts', category: 'judai', enabled: true },
  { id: 'ch_11', name: 'Bhojpuri Chaukhat Comedy', youtubeHandleOrUrl: 'bhojpuri gaon chaukhat comedy shorts', category: 'comedy', enabled: true },
  { id: 'ch_12', name: 'Bhojpuri Sher Shayari', youtubeHandleOrUrl: 'bhojpuri sher shayari attitude reels', category: 'rangdari', enabled: true },
];

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_KV)) {
        db.createObjectStore(STORE_KV);
      }
      if (!db.objectStoreNames.contains(STORE_REELS)) {
        db.createObjectStore(STORE_REELS, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORE_PHOTOS)) {
        db.createObjectStore(STORE_PHOTOS, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function kvGet<T>(key: string, fallback: T): Promise<T> {
  try {
    const db = await openDb();
    return await new Promise((resolve) => {
      const tx = db.transaction(STORE_KV, 'readonly');
      const req = tx.objectStore(STORE_KV).get(key);
      req.onsuccess = () => resolve(req.result !== undefined ? (req.result as T) : fallback);
      req.onerror = () => resolve(fallback);
    });
  } catch {
    return fallback;
  }
}

async function kvSet<T>(key: string, value: T): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_KV, 'readwrite');
    tx.objectStore(STORE_KV).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export const loadVault = () => kvGet<ApiVault>('vault', DEFAULT_VAULT);
export const saveVault = (vault: ApiVault) => kvSet('vault', vault);

export const loadFbPages = () => kvGet<FacebookPageSlot[]>('fbPages', []);
export const saveFbPages = (pages: FacebookPageSlot[]) => kvSet('fbPages', pages);

export const loadChannels = () => kvGet<ResearchChannel[]>('channels', DEFAULT_CHANNELS);
export const saveChannels = (channels: ResearchChannel[]) => kvSet('channels', channels);

export const loadSchedule = () => kvGet<ScheduleConfig>('schedule', DEFAULT_SCHEDULE);
export const saveSchedule = (schedule: ScheduleConfig) => kvSet('schedule', schedule);

export async function loadReelsHistory(): Promise<ReelHistoryItem[]> {
  try {
    const db = await openDb();
    const items = await new Promise<ReelHistoryItem[]>((resolve) => {
      const tx = db.transaction(STORE_REELS, 'readonly');
      const req = tx.objectStore(STORE_REELS).getAll();
      req.onsuccess = () => resolve((req.result as ReelHistoryItem[]) || []);
      req.onerror = () => resolve([]);
    });
    return items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } catch {
    return [];
  }
}

export async function mergeReelsHistory(incoming: ReelHistoryItem[]): Promise<ReelHistoryItem[]> {
  const db = await openDb();
  const existing = await loadReelsHistory();
  const map = new Map<string, ReelHistoryItem>();
  for (const item of existing) map.set(item.id, item);
  for (const item of incoming) {
    const prev = map.get(item.id);
    map.set(item.id, { ...prev, ...item, savedLocally: prev?.savedLocally || item.savedLocally });
  }
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_REELS, 'readwrite');
    const store = tx.objectStore(STORE_REELS);
    for (const val of map.values()) {
      store.put(val);
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  return Array.from(map.values()).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function loadPhotoPosts(): Promise<PhotoPostItem[]> {
  try {
    const db = await openDb();
    const items = await new Promise<PhotoPostItem[]>((resolve) => {
      const tx = db.transaction(STORE_PHOTOS, 'readonly');
      const req = tx.objectStore(STORE_PHOTOS).getAll();
      req.onsuccess = () => resolve((req.result as PhotoPostItem[]) || []);
      req.onerror = () => resolve([]);
    });
    return items.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  } catch {
    return [];
  }
}

export async function mergePhotoPosts(incoming: PhotoPostItem[]): Promise<PhotoPostItem[]> {
  const db = await openDb();
  const existing = await loadPhotoPosts();
  const map = new Map<string, PhotoPostItem>();
  for (const item of existing) map.set(item.id, item);
  for (const item of incoming) map.set(item.id, { ...map.get(item.id), ...item });
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_PHOTOS, 'readwrite');
    const store = tx.objectStore(STORE_PHOTOS);
    for (const val of map.values()) store.put(val);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  return Array.from(map.values()).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const res = String(reader.result || '');
      resolve(res.includes(',') ? res.split(',')[1] : res);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export async function saveReelToPhone(item: ReelHistoryItem): Promise<{ ok: boolean; message: string }> {
  if (!item.videoDownloadUrl) {
    return { ok: false, message: 'Video URL abhi uplabdh nahi hai.' };
  }
  try {
    const resp = await fetch(item.videoDownloadUrl);
    if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
    const blob = await resp.blob();
    const safeName = `bhojpuri-reel-${item.id}.mp4`;

    try {
      const base64Data = await blobToBase64(blob);
      await Filesystem.writeFile({
        path: `BhojpuriReelStudio/${safeName}`,
        data: base64Data,
        directory: Directory.Documents,
        recursive: true,
      });
      await mergeReelsHistory([{ ...item, savedLocally: true }]);
      return { ok: true, message: `Phone Documents/BhojpuriReelStudio/${safeName} me save ho gaya!` };
    } catch {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = safeName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      await mergeReelsHistory([{ ...item, savedLocally: true }]);
      return { ok: true, message: `${safeName} download ho gaya!` };
    }
  } catch (err) {
    return { ok: false, message: err instanceof Error ? err.message : 'Save error' };
  }
}

export async function shareReelFallback(item: ReelHistoryItem): Promise<void> {
  const text = `${item.title}\n\n${item.caption}\n${item.hashtags.join(' ')}\n${item.videoDownloadUrl || ''}`;
  try {
    await Share.share({
      title: item.title,
      text,
      url: item.videoDownloadUrl || undefined,
      dialogTitle: 'Share Bhojpuri Reel',
    });
  } catch {
    if (navigator.share) {
      await navigator.share({ title: item.title, text, url: item.videoDownloadUrl });
    } else if (navigator.clipboard) {
      await navigator.clipboard.writeText(text);
    }
  }
}
