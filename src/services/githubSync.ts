import sealedbox from 'tweetnacl-sealedbox-js';
import type {
  ApiVault,
  CloudWorkflowStatus,
  FacebookPageSlot,
  PhotoPostItem,
  ReelHistoryItem,
  ResearchChannel,
  ScheduleConfig,
} from '../types/studio';

function ghHeaders(pat: string): Record<string, string> {
  return {
    Authorization: `Bearer ${pat.trim()}`,
    Accept: 'application/vnd.github+json',
    'Content-Type': 'application/json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function bytesToBase64(bytes: Uint8Array): string {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

function utf8ToBase64(str: string): string {
  const bytes = new TextEncoder().encode(str);
  return bytesToBase64(bytes);
}

function base64ToUtf8(b64: string): string {
  const clean = b64.replace(/\n/g, '');
  return new TextDecoder().decode(base64ToBytes(clean));
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = 15000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function pushRepoSecret(
  repo: string,
  pat: string,
  keyId: string,
  publicKeyB64: string,
  secretName: string,
  secretValue: string,
): Promise<void> {
  const pubKeyBytes = base64ToBytes(publicKeyB64);
  const msgBytes = new TextEncoder().encode(secretValue.trim());
  const encryptedBytes = sealedbox.seal(msgBytes, pubKeyBytes);
  const encryptedB64 = bytesToBase64(encryptedBytes);

  const res = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/actions/secrets/${secretName}`,
    {
      method: 'PUT',
      headers: ghHeaders(pat),
      body: JSON.stringify({ encrypted_value: encryptedB64, key_id: keyId }),
    },
  );
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Secret ${secretName} failed (${res.status}): ${errText}`);
  }
}

async function upsertRepoFile(
  repo: string,
  pat: string,
  path: string,
  content: string,
  commitMessage: string,
): Promise<void> {
  let sha: string | undefined;
  const getRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/contents/${path}`,
    { method: 'GET', headers: ghHeaders(pat) },
  );
  if (getRes.ok) {
    const data = (await getRes.json()) as { sha?: string };
    sha = data.sha;
  }

  const putRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/contents/${path}`,
    {
      method: 'PUT',
      headers: ghHeaders(pat),
      body: JSON.stringify({
        message: commitMessage,
        content: utf8ToBase64(content),
        ...(sha ? { sha } : {}),
      }),
    },
  );
  if (!putRes.ok) {
    const errText = await putRes.text();
    throw new Error(`File ${path} push failed (${putRes.status}): ${errText}`);
  }
}

export async function syncAllToGitHub(params: {
  vault: ApiVault;
  fbPages: FacebookPageSlot[];
  channels: ResearchChannel[];
  schedule: ScheduleConfig;
}): Promise<{ ok: boolean; syncedSecrets: string[]; message: string }> {
  const { vault, fbPages, channels, schedule } = params;
  const pat = vault.githubPat.trim();
  const repo = vault.githubRepo.trim();

  if (!pat || !repo.includes('/')) {
    return { ok: false, syncedSecrets: [], message: 'Pehle GitHub PAT aur Repo (owner/repo) save karein.' };
  }

  const keyRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/actions/secrets/public-key`,
    { method: 'GET', headers: ghHeaders(pat) },
  );
  if (!keyRes.ok) {
    const txt = await keyRes.text();
    return {
      ok: false,
      syncedSecrets: [],
      message: `GitHub Repo access failed (${keyRes.status}). Check PAT & Repo name. ${txt}`,
    };
  }
  const { key_id, key } = (await keyRes.json()) as { key_id: string; key: string };

  const activePage = fbPages.find((p) => p.isActive) || fbPages[0];
  const secretsToPush: Array<[string, string]> = [];

  if (vault.groqApiKey.trim()) secretsToPush.push(['GROQ_API_KEY', vault.groqApiKey]);
  if (vault.geminiApiKey.trim()) secretsToPush.push(['GEMINI_API_KEY', vault.geminiApiKey]);
  if (vault.cloudflareAccountId.trim()) secretsToPush.push(['CLOUDFLARE_ACCOUNT_ID', vault.cloudflareAccountId]);
  if (vault.cloudflareApiToken.trim()) secretsToPush.push(['CLOUDFLARE_API_TOKEN', vault.cloudflareApiToken]);
  if (activePage?.pageId.trim()) secretsToPush.push(['FB_PAGE_ID', activePage.pageId]);
  if (activePage?.pageAccessToken.trim()) secretsToPush.push(['FB_PAGE_ACCESS_TOKEN', activePage.pageAccessToken]);
  secretsToPush.push(['GH_AUTO_PAT', pat]);

  const syncedSecrets: string[] = [];
  for (const [name, val] of secretsToPush) {
    await pushRepoSecret(repo, pat, key_id, key, name, val);
    syncedSecrets.push(name);
  }

  const configPayload = {
    updatedAt: new Date().toISOString(),
    activeFacebookPage: activePage
      ? { id: activePage.id, pageName: activePage.pageName, pageId: activePage.pageId }
      : null,
    schedule,
    channels: channels.filter((c) => c.enabled),
  };

  await upsertRepoFile(
    repo,
    pat,
    'data/config.json',
    JSON.stringify(configPayload, null, 2),
    'chore: sync config and active Facebook page from Bhojpuri ReelStudio APK',
  );

  return {
    ok: true,
    syncedSecrets,
    message: `${syncedSecrets.length} Secrets + config.json GitHub par sync ho gaya!`,
  };
}

export async function triggerCloudWorkflow(
  vault: ApiVault,
  workflowFile: 'bhojpuri-auto-reel.yml' | 'photo-post.yml',
  slot: 'morning' | 'evening' | 'manual' = 'manual',
): Promise<{ ok: boolean; message: string }> {
  const pat = vault.githubPat.trim();
  const repo = vault.githubRepo.trim();
  if (!pat || !repo) return { ok: false, message: 'GitHub PAT aur Repo set nahi hai.' };

  const res = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflowFile}/dispatches`,
    {
      method: 'POST',
      headers: ghHeaders(pat),
      body: JSON.stringify(
        workflowFile === 'bhojpuri-auto-reel.yml'
          ? { ref: 'main', inputs: { slot } }
          : { ref: 'main' },
      ),
    },
  );
  if (!res.ok) {
    const err = await res.text();
    return { ok: false, message: `Trigger failed (${res.status}): ${err}` };
  }
  return { ok: true, message: `${workflowFile} cloud par start ho gaya! 2-4 minute me Feed refresh karein.` };
}

export async function fetchCloudStatusAndHistory(vault: ApiVault): Promise<{
  workflow: CloudWorkflowStatus;
  reels: ReelHistoryItem[];
  photos: PhotoPostItem[];
}> {
  const pat = vault.githubPat.trim();
  const repo = vault.githubRepo.trim();
  if (!pat || !repo) {
    return { workflow: { state: 'idle' }, reels: [], photos: [] };
  }

  let workflow: CloudWorkflowStatus = { state: 'idle' };
  const runsRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/actions/runs?per_page=3`,
    { method: 'GET', headers: ghHeaders(pat) },
  );
  if (runsRes.ok) {
    const runsJson = (await runsRes.json()) as {
      workflow_runs?: Array<{
        status: CloudWorkflowStatus['state'];
        conclusion?: string;
        html_url: string;
        updated_at: string;
        name: string;
      }>;
    };
    const latest = runsJson.workflow_runs?.[0];
    if (latest) {
      workflow = {
        state: latest.status,
        conclusion: latest.conclusion,
        runUrl: latest.html_url,
        updatedAt: latest.updated_at,
        name: latest.name,
      };
    }
  }

  let reels: ReelHistoryItem[] = [];
  const histRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/contents/data/history.json`,
    { method: 'GET', headers: ghHeaders(pat) },
  );
  if (histRes.ok) {
    const fileJson = (await histRes.json()) as { content?: string };
    if (fileJson.content) {
      try {
        reels = JSON.parse(base64ToUtf8(fileJson.content)) as ReelHistoryItem[];
      } catch {
        reels = [];
      }
    }
  }

  let photos: PhotoPostItem[] = [];
  const photoRes = await fetchWithTimeout(
    `https://api.github.com/repos/${repo}/contents/data/photo_history.json`,
    { method: 'GET', headers: ghHeaders(pat) },
  );
  if (photoRes.ok) {
    const fileJson = (await photoRes.json()) as { content?: string };
    if (fileJson.content) {
      try {
        photos = JSON.parse(base64ToUtf8(fileJson.content)) as PhotoPostItem[];
      } catch {
        photos = [];
      }
    }
  }

  return { workflow, reels, photos };
}
