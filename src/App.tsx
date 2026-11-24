import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BarChart3,
  CheckCircle2,
  CloudUpload,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Film,
  Image as ImageIcon,
  KeyRound,
  Play,
  Plus,
  RefreshCw,
  Save,
  Share2,
  Sparkles,
  Trash2,
  Tv,
  XCircle,
} from 'lucide-react';
import type {
  ApiVault,
  CloudWorkflowStatus,
  FacebookPageSlot,
  MoodCategory,
  PhotoPostItem,
  ReelHistoryItem,
  ResearchChannel,
  ScheduleConfig,
} from './types/studio';
import {
  DEFAULT_CHANNELS,
  DEFAULT_SCHEDULE,
  DEFAULT_VAULT,
  loadChannels,
  loadFbPages,
  loadPhotoPosts,
  loadReelsHistory,
  loadSchedule,
  loadVault,
  mergePhotoPosts,
  mergeReelsHistory,
  saveChannels,
  saveFbPages,
  saveReelToPhone,
  saveSchedule,
  saveVault,
  shareReelFallback,
} from './services/localMemory';
import {
  fetchCloudStatusAndHistory,
  syncAllToGitHub,
  triggerCloudWorkflow,
} from './services/githubSync';
import { VideoModal } from './components/VideoModal';

type TabKey = 'feed' | 'reach' | 'channels' | 'vault';

const MOOD_COLORS: Record<MoodCategory, string> = {
  rangdari: 'bg-rose-50 text-rose-700 border-rose-200',
  bewafai: 'bg-amber-50 text-amber-800 border-amber-200',
  judai: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  vafadari: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  comedy: 'bg-sky-50 text-sky-700 border-sky-200',
};

const WEEK_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export default function App() {
  const [tab, setTab] = useState<TabKey>('feed');
  const [vault, setVault] = useState<ApiVault>(DEFAULT_VAULT);
  const [fbPages, setFbPages] = useState<FacebookPageSlot[]>([]);
  const [channels, setChannels] = useState<ResearchChannel[]>(DEFAULT_CHANNELS);
  const [schedule, setSchedule] = useState<ScheduleConfig>(DEFAULT_SCHEDULE);
  const [reels, setReels] = useState<ReelHistoryItem[]>([]);
  const [photos, setPhotos] = useState<PhotoPostItem[]>([]);
  const [workflow, setWorkflow] = useState<CloudWorkflowStatus>({ state: 'idle' });

  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);
  const [activeVideo, setActiveVideo] = useState<ReelHistoryItem | null>(null);

  // Add new channel inputs
  const [newChName, setNewChName] = useState('');
  const [newChQuery, setNewChQuery] = useState('');
  const [newChCat, setNewChCat] = useState<MoodCategory>('rangdari');

  // Add new FB page name
  const [newPageName, setNewPageName] = useState('');

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(''), 3500);
  };

  useEffect(() => {
    let alive = true;
    (async () => {
      const [v, fp, ch, sc, rh, ph] = await Promise.all([
        loadVault(),
        loadFbPages(),
        loadChannels(),
        loadSchedule(),
        loadReelsHistory(),
        loadPhotoPosts(),
      ]);
      if (!alive) return;
      setVault(v);
      setFbPages(fp);
      setChannels(ch);
      setSchedule(sc);
      setReels(rh);
      setPhotos(ph);
    })();
    return () => {
      alive = false;
    };
  }, []);

  const activePage = useMemo(
    () => fbPages.find((p) => p.isActive) || fbPages[0] || null,
    [fbPages],
  );

  const reachByMood = useMemo(() => {
    const map: Record<MoodCategory, { count: number; views: number; likes: number; shares: number }> = {
      rangdari: { count: 0, views: 0, likes: 0, shares: 0 },
      bewafai: { count: 0, views: 0, likes: 0, shares: 0 },
      judai: { count: 0, views: 0, likes: 0, shares: 0 },
      vafadari: { count: 0, views: 0, likes: 0, shares: 0 },
      comedy: { count: 0, views: 0, likes: 0, shares: 0 },
    };
    for (const r of reels) {
      const m = map[r.mood];
      if (!m) continue;
      m.count += 1;
      m.views += r.reachMetrics?.views || 0;
      m.likes += r.reachMetrics?.likes || 0;
      m.shares += r.reachMetrics?.shares || 0;
    }
    return map;
  }, [reels]);

  // Individual single-field save for Vault keys/IDs
  const handleSaveVaultField = async (field: keyof ApiVault, label: string) => {
    const next = { ...vault };
    await saveVault(next);
    showToast(`${label} local memory me save ho gaya!`);
  };

  const handleAddFbPage = async () => {
    const name = newPageName.trim() || `Bhojpuri Page ${fbPages.length + 1}`;
    const slot: FacebookPageSlot = {
      id: `pg_${Date.now()}`,
      pageName: name,
      pageId: '',
      pageAccessToken: '',
      isActive: fbPages.length === 0,
      updatedAt: new Date().toISOString(),
    };
    const next = [...fbPages, slot];
    setFbPages(next);
    await saveFbPages(next);
    setNewPageName('');
    showToast(`"${name}" slot add ho gaya!`);
  };

  const handleUpdatePageField = (id: string, field: 'pageName' | 'pageId' | 'pageAccessToken', val: string) => {
    setFbPages((prev) =>
      prev.map((p) => (p.id === id ? { ...p, [field]: val, updatedAt: new Date().toISOString() } : p)),
    );
  };

  const handleSaveFbPages = async (msg: string) => {
    await saveFbPages(fbPages);
    showToast(msg);
  };

  const handleSetActivePage = async (id: string) => {
    const next = fbPages.map((p) => ({ ...p, isActive: p.id === id }));
    setFbPages(next);
    await saveFbPages(next);
    const chosen = next.find((p) => p.id === id);
    showToast(`Active Page set: ${chosen?.pageName || 'Selected'}. Ab "Sync to GitHub" dabayein!`);
  };

  const handleDeletePage = async (id: string) => {
    const filtered = fbPages.filter((p) => p.id !== id);
    if (filtered.length > 0 && !filtered.some((p) => p.isActive)) {
      filtered[0].isActive = true;
    }
    setFbPages(filtered);
    await saveFbPages(filtered);
    showToast('Page slot hata diya gaya.');
  };

  const handleSaveSchedule = async () => {
    await saveSchedule(schedule);
    showToast('Schedule settings save ho gayi!');
  };

  const handleToggleDay = (day: string) => {
    const exists = schedule.photoPostDays.includes(day);
    const nextDays = exists
      ? schedule.photoPostDays.filter((d) => d !== day)
      : [...schedule.photoPostDays, day];
    setSchedule({ ...schedule, photoPostDays: nextDays });
  };

  const handleAddChannel = async () => {
    if (!newChName.trim() || !newChQuery.trim()) {
      showToast('Channel naam aur search/URL dono bharein.');
      return;
    }
    const next: ResearchChannel[] = [
      ...channels,
      {
        id: `ch_${Date.now()}`,
        name: newChName.trim(),
        youtubeHandleOrUrl: newChQuery.trim(),
        category: newChCat,
        enabled: true,
      },
    ];
    setChannels(next);
    await saveChannels(next);
    setNewChName('');
    setNewChQuery('');
    showToast('Naya Bhojpuri channel add aur save ho gaya!');
  };

  const handleToggleChannel = async (id: string) => {
    const next = channels.map((c) => (c.id === id ? { ...c, enabled: !c.enabled } : c));
    setChannels(next);
    await saveChannels(next);
  };

  const handleDeleteChannel = async (id: string) => {
    const next = channels.filter((c) => c.id !== id);
    setChannels(next);
    await saveChannels(next);
    showToast('Channel list se hataya gaya.');
  };

  const handleSyncToGitHub = async () => {
    setBusy(true);
    try {
      const res = await syncAllToGitHub({ vault, fbPages, channels, schedule });
      showToast(res.message);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'GitHub sync error');
    } finally {
      setBusy(false);
    }
  };

  const handleRefreshCloud = async () => {
    setBusy(true);
    try {
      const data = await fetchCloudStatusAndHistory(vault);
      setWorkflow(data.workflow);
      if (data.reels.length > 0) {
        const merged = await mergeReelsHistory(data.reels);
        setReels(merged);
      }
      if (data.photos.length > 0) {
        const mergedPhotos = await mergePhotoPosts(data.photos);
        setPhotos(mergedPhotos);
      }
      showToast('Cloud status aur permanent history sync ho gayi!');
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Refresh error');
    } finally {
      setBusy(false);
    }
  };

  const handleRunNow = async (wf: 'bhojpuri-auto-reel.yml' | 'photo-post.yml') => {
    setBusy(true);
    try {
      const res = await triggerCloudWorkflow(vault, wf, 'manual');
      showToast(res.message);
      if (res.ok) {
        const data = await fetchCloudStatusAndHistory(vault);
        setWorkflow(data.workflow);
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Trigger error');
    } finally {
      setBusy(false);
    }
  };

  const handleSavePhone = async (item: ReelHistoryItem) => {
    setBusy(true);
    try {
      const res = await saveReelToPhone(item);
      showToast(res.message);
      const updated = await loadReelsHistory();
      setReels(updated);
    } finally {
      setBusy(false);
    }
  };

  const renderSecretRow = (
    field: keyof ApiVault,
    label: string,
    placeholder: string,
    buttonLabel: string,
    isSecret = true,
  ) => {
    const val = vault[field];
    const isSaved = val.trim().length > 0;
    const isShown = !!revealed[field];

    return (
      <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-bold text-[#050505]">{label}</span>
          <span
            className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
              isSaved
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-amber-50 text-amber-700 border-amber-200'
            }`}
          >
            {isSaved ? 'Saved ✅' : 'Not Set'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <input
            type={isSecret && !isShown ? 'password' : 'text'}
            value={val}
            onChange={(e) => setVault({ ...vault, [field]: e.target.value })}
            placeholder={placeholder}
            className="flex-1 px-3 py-2 text-sm bg-[#F0F2F5] border border-[#CED0D4] rounded-lg text-[#050505] focus:outline-none focus:border-[#1877F2]"
          />
          {isSecret && (
            <button
              type="button"
              onClick={() => setRevealed({ ...revealed, [field]: !isShown })}
              className="p-2 rounded-lg bg-[#F0F2F5] border border-[#CED0D4] text-[#65676B]"
              aria-label={`Toggle ${label}`}
            >
              {isShown ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={() => handleSaveVaultField(field, label)}
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
        >
          <Save className="w-3.5 h-3.5" />
          {buttonLabel}
        </button>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#F0F2F5] text-[#050505] overflow-x-hidden">
      {/* Facebook-style Pure White Top Header */}
      <header className="sticky top-0 z-30 bg-white border-b border-[#CED0D4] px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl font-extrabold tracking-tight text-[#1877F2]">
            Bhojpuri ReelStudio
          </span>
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
            24x7 AUTO
          </span>
        </div>
        <button
          type="button"
          onClick={handleRefreshCloud}
          disabled={busy}
          className="flex items-center gap-1 px-3 py-1.5 rounded-full bg-[#F0F2F5] border border-[#CED0D4] text-xs font-bold text-[#050505]"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-[#1877F2] ${busy ? 'animate-spin' : ''}`} />
          Sync
        </button>
      </header>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed top-14 left-3 right-3 z-50 bg-[#1877F2] text-white text-xs font-bold px-4 py-2.5 rounded-xl border border-blue-700 text-center">
          {toast}
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-xl mx-auto p-3 pb-24 space-y-3">
        {tab === 'feed' && (
          <>
            {/* Summary Card */}
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-[#F0F2F5] rounded-lg p-2 border border-[#CED0D4]">
                  <p className="text-lg font-extrabold text-[#1877F2]">{reels.length}</p>
                  <p className="text-[11px] font-semibold text-[#65676B]">Saved Reels</p>
                </div>
                <div className="bg-[#F0F2F5] rounded-lg p-2 border border-[#CED0D4]">
                  <p className="text-xs font-extrabold text-[#050505] truncate">
                    {activePage ? activePage.pageName : 'No Page'}
                  </p>
                  <p className="text-[11px] font-semibold text-[#65676B]">Active FB Page</p>
                </div>
                <div className="bg-[#F0F2F5] rounded-lg p-2 border border-[#CED0D4]">
                  <p className="text-xs font-extrabold text-[#42B72A]">
                    {schedule.morningReelIst} / {schedule.eveningReelIst}
                  </p>
                  <p className="text-[11px] font-semibold text-[#65676B]">Daily IST</p>
                </div>
              </div>

              {/* Cloud Runner Status & Quick Actions */}
              <div className="flex items-center justify-between bg-[#F0F2F5] border border-[#CED0D4] rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-[#1877F2]" />
                  <div>
                    <p className="text-xs font-bold text-[#050505]">
                      Cloud Status: <span className="uppercase text-[#1877F2]">{workflow.state}</span>
                      {workflow.conclusion ? ` (${workflow.conclusion})` : ''}
                    </p>
                    <p className="text-[11px] text-[#65676B]">
                      {workflow.name || '24x7 GitHub Cloud Pipeline'}
                    </p>
                  </div>
                </div>
                {workflow.runUrl && (
                  <a
                    href={workflow.runUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs font-bold text-[#1877F2] flex items-center gap-1"
                  >
                    Logs <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>

              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRunNow('bhojpuri-auto-reel.yml')}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                >
                  <Sparkles className="w-4 h-4" />
                  Abhi Reel Banayein
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => handleRunNow('photo-post.yml')}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-[#42B72A] text-white text-xs font-bold"
                >
                  <ImageIcon className="w-4 h-4" />
                  Abhi Photo Post
                </button>
              </div>
            </div>

            {/* Reels Permanent History Feed */}
            {reels.length === 0 ? (
              <div className="bg-white border border-[#CED0D4] rounded-xl p-6 text-center space-y-2">
                <Film className="w-8 h-8 text-[#1877F2] mx-auto" />
                <h3 className="text-sm font-bold text-[#050505]">Abhi koi Reel history nahi hai</h3>
                <p className="text-xs text-[#65676B]">
                  "Vault" tab me apni Keys save karke "Sync All to GitHub" dabayein, fir "Abhi Reel Banayein" chalayein. Har video aur research report yahan hamesha save rahegi.
                </p>
              </div>
            ) : (
              reels.map((item) => (
                <article
                  key={item.id}
                  className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-1.5 flex-wrap mb-1">
                        <span
                          className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                            MOOD_COLORS[item.mood]
                          }`}
                        >
                          {item.mood}
                        </span>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#F0F2F5] border border-[#CED0D4] text-[#65676B] uppercase">
                          {item.slot}
                        </span>
                        {item.savedLocally && (
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Saved on Phone ✅
                          </span>
                        )}
                      </div>
                      <h3 className="text-sm font-bold text-[#050505]">{item.title}</h3>
                      <p className="text-[11px] text-[#65676B]">
                        {new Date(item.createdAt).toLocaleString('en-IN')}
                      </p>
                    </div>
                  </div>

                  {/* Step-by-Step Status Badges */}
                  <div className="grid grid-cols-4 gap-1.5 text-center">
                    {[
                      { label: 'Script', ok: item.status.script },
                      { label: 'Media', ok: item.status.media },
                      { label: 'Render', ok: item.status.render },
                      { label: 'FB Post', ok: item.status.fbUpload },
                    ].map((st) => (
                      <div
                        key={st.label}
                        className={`flex items-center justify-center gap-1 py-1 rounded-lg border text-[11px] font-bold ${
                          st.ok
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border-rose-200'
                        }`}
                      >
                        {st.ok ? (
                          <CheckCircle2 className="w-3 h-3" />
                        ) : (
                          <XCircle className="w-3 h-3" />
                        )}
                        {st.label}
                      </div>
                    ))}
                  </div>

                  {item.status.error && (
                    <div className="text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded-lg p-2">
                      FB Upload Note: {item.status.error}
                    </div>
                  )}

                  {/* Research Base Card */}
                  <div className="bg-[#F0F2F5] border border-[#CED0D4] rounded-lg p-2.5 space-y-1">
                    <p className="text-[11px] font-bold text-[#1877F2]">
                      Kis Video Ko Base Banaya Gaya:
                    </p>
                    <p className="text-xs font-semibold text-[#050505]">
                      {item.researchSource.channelName} — {item.researchSource.videoTitle}
                    </p>
                    <div className="flex items-center justify-between text-[11px] text-[#65676B]">
                      <span>{item.researchSource.viewsLabel}</span>
                      {item.researchSource.videoUrl && (
                        <a
                          href={item.researchSource.videoUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[#1877F2] font-bold flex items-center gap-1"
                        >
                          Source Dekhein <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Viral Gap Analysis */}
                  {item.gapAnalysis.length > 0 && (
                    <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 space-y-1">
                      <p className="text-[11px] font-bold text-amber-800">
                        Viral Gap Analysis (Kya Kami Thi aur Kya Sudhara):
                      </p>
                      <ul className="list-disc pl-4 space-y-0.5 text-xs text-[#050505]">
                        {item.gapAnalysis.map((g, idx) => (
                          <li key={idx}>{g}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setActiveVideo(item)}
                      className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                    >
                      <Play className="w-3.5 h-3.5" />
                      Video Dekhein
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSavePhone(item)}
                      className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-[#F0F2F5] border border-[#CED0D4] text-[#050505] text-xs font-bold"
                    >
                      <Download className="w-3.5 h-3.5 text-[#1877F2]" />
                      Phone Save
                    </button>
                    <button
                      type="button"
                      onClick={() => shareReelFallback(item)}
                      className="px-3 flex items-center justify-center gap-1 py-2 rounded-lg bg-[#42B72A] text-white text-xs font-bold"
                    >
                      <Share2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </article>
              ))
            )}
          </>
        )}

        {tab === 'reach' && (
          <>
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <h2 className="text-base font-bold text-[#1877F2]">
                Facebook Page Reach & Mood Performance
              </h2>
              <p className="text-xs text-[#65676B]">
                System har naya video banane se pehle aapke Facebook Page ke views, likes aur shares padhta hai taaki jo mood chal raha hai use aur tez kare.
              </p>
              <div className="space-y-2">
                {(Object.keys(reachByMood) as MoodCategory[]).map((mood) => {
                  const row = reachByMood[mood];
                  return (
                    <div
                      key={mood}
                      className="flex items-center justify-between bg-[#F0F2F5] border border-[#CED0D4] rounded-lg px-3 py-2"
                    >
                      <span
                        className={`text-xs font-bold uppercase px-2 py-0.5 rounded-full border ${MOOD_COLORS[mood]}`}
                      >
                        {mood}
                      </span>
                      <div className="text-xs font-semibold text-[#050505] space-x-3">
                        <span>Reels: {row.count}</span>
                        <span>Views: {row.views}</span>
                        <span>Shares: {row.shares}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Monetization & Photo Post Settings */}
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-bold text-[#050505]">
                  Photo Post & Page Monetization Helper
                </h2>
                <button
                  type="button"
                  onClick={() =>
                    setSchedule({ ...schedule, photoPostEnabled: !schedule.photoPostEnabled })
                  }
                  className={`px-3 py-1 rounded-full text-xs font-bold ${
                    schedule.photoPostEnabled
                      ? 'bg-[#42B72A] text-white'
                      : 'bg-[#F0F2F5] border border-[#CED0D4] text-[#65676B]'
                  }`}
                >
                  {schedule.photoPostEnabled ? 'ON' : 'OFF'}
                </button>
              </div>
              <p className="text-xs text-[#65676B]">
                Hafte me 2–3 din Bhojpuri Shayari/Quote photo + engagement caption post hota rahega.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {WEEK_DAYS.map((d) => {
                  const active = schedule.photoPostDays.includes(d);
                  return (
                    <button
                      key={d}
                      type="button"
                      onClick={() => handleToggleDay(d)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold border ${
                        active
                          ? 'bg-[#1877F2] text-white border-[#1877F2]'
                          : 'bg-[#F0F2F5] text-[#050505] border-[#CED0D4]'
                      }`}
                    >
                      {d}
                    </button>
                  );
                })}
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs font-bold text-[#050505]">Photo Time (IST):</label>
                <input
                  type="time"
                  value={schedule.photoPostIst}
                  onChange={(e) => setSchedule({ ...schedule, photoPostIst: e.target.value })}
                  className="px-2.5 py-1.5 rounded-lg bg-[#F0F2F5] border border-[#CED0D4] text-xs font-bold"
                />
                <button
                  type="button"
                  onClick={handleSaveSchedule}
                  className="ml-auto px-3 py-1.5 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                >
                  Save Photo Plan
                </button>
              </div>

              {photos.length > 0 && (
                <div className="pt-2 border-t border-[#CED0D4] space-y-2">
                  <p className="text-xs font-bold text-[#050505]">Recent Photo Posts</p>
                  {photos.slice(0, 5).map((ph) => (
                    <div
                      key={ph.id}
                      className="bg-[#F0F2F5] border border-[#CED0D4] rounded-lg p-2.5 text-xs space-y-1"
                    >
                      <p className="font-bold text-[#050505]">{ph.quoteText}</p>
                      <p className="text-[#65676B]">{ph.caption}</p>
                      <span
                        className={`inline-block text-[10px] font-bold px-2 py-0.5 rounded-full ${
                          ph.fbPublished
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border border-rose-200'
                        }`}
                      >
                        {ph.fbPublished ? 'FB Published ✅' : ph.error || 'Pending'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        {tab === 'channels' && (
          <>
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <h2 className="text-base font-bold text-[#1877F2]">
                10–15 Popular Bhojpuri Research Channels
              </h2>
              <p className="text-xs text-[#65676B]">
                Cloud script inhi active channels aur topics se sabse zyada viral video dhoondh kar uska Viral Gap Analysis karti hai aur naya original dialogue banati hai.
              </p>
              <div className="space-y-2">
                <input
                  type="text"
                  value={newChName}
                  onChange={(e) => setNewChName(e.target.value)}
                  placeholder="Channel / Page ka naam (e.g. Khesari Dialogue)"
                  className="w-full px-3 py-2 text-sm bg-[#F0F2F5] border border-[#CED0D4] rounded-lg"
                />
                <input
                  type="text"
                  value={newChQuery}
                  onChange={(e) => setNewChQuery(e.target.value)}
                  placeholder="YouTube search keyword ya channel URL"
                  className="w-full px-3 py-2 text-sm bg-[#F0F2F5] border border-[#CED0D4] rounded-lg"
                />
                <div className="flex gap-2">
                  <select
                    value={newChCat}
                    onChange={(e) => setNewChCat(e.target.value as MoodCategory)}
                    className="px-3 py-2 text-xs font-bold bg-[#F0F2F5] border border-[#CED0D4] rounded-lg"
                  >
                    <option value="rangdari">Rangdari</option>
                    <option value="bewafai">Bewafai</option>
                    <option value="judai">Judai</option>
                    <option value="vafadari">Vafadari</option>
                    <option value="comedy">Comedy</option>
                  </select>
                  <button
                    type="button"
                    onClick={handleAddChannel}
                    className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                  >
                    <Plus className="w-4 h-4" />
                    Channel Add Karein
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              {channels.map((ch) => (
                <div
                  key={ch.id}
                  className="bg-white border border-[#CED0D4] rounded-xl p-3 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${
                          MOOD_COLORS[ch.category]
                        }`}
                      >
                        {ch.category}
                      </span>
                      <p className="text-sm font-bold text-[#050505] truncate">{ch.name}</p>
                    </div>
                    <p className="text-xs text-[#65676B] truncate mt-0.5">{ch.youtubeHandleOrUrl}</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => handleToggleChannel(ch.id)}
                      className={`px-2.5 py-1 rounded-lg text-xs font-bold ${
                        ch.enabled
                          ? 'bg-[#42B72A] text-white'
                          : 'bg-[#F0F2F5] border border-[#CED0D4] text-[#65676B]'
                      }`}
                    >
                      {ch.enabled ? 'ON' : 'OFF'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDeleteChannel(ch.id)}
                      className="p-1.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-700"
                      aria-label="Delete channel"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {tab === 'vault' && (
          <>
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-xs font-semibold text-emerald-800">
              Auto-Rotation Active: Koi model chunne ki zaroorat nahi — system khud aapki saved active keys se best working AI model rotate karta hai.
            </div>

            {renderSecretRow('githubPat', '1. GitHub Personal Access Token (PAT)', 'ghp_xxxxxxxxxxxx', 'Save GitHub PAT')}
            {renderSecretRow('githubRepo', '2. GitHub Repo (owner/repo)', 'sarfealam2246-coder/bhojpuri-auto-reels', 'Save GitHub Repo', false)}
            {renderSecretRow('groqApiKey', '3. Groq API Key', 'gsk_xxxxxxxxxxxx', 'Save Groq Key')}
            {renderSecretRow('geminiApiKey', '4. Google Gemini API Key', 'AIzaSyxxxxxxxxxxxx', 'Save Gemini Key')}
            {renderSecretRow('cloudflareAccountId', '5A. Cloudflare Workers AI — Account ID', '32-char Account ID', 'Save Account ID', false)}
            {renderSecretRow('cloudflareApiToken', '5B. Cloudflare Workers AI — API Token', 'Cloudflare API Token', 'Save API Token')}

            {/* Multi-Page Facebook Switcher */}
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-[#1877F2]">
                  6. Facebook Page Switcher (Multi-Page)
                </h3>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newPageName}
                  onChange={(e) => setNewPageName(e.target.value)}
                  placeholder="Naya Page Name (e.g. Bhojpuri Tadka)"
                  className="flex-1 px-3 py-2 text-sm bg-[#F0F2F5] border border-[#CED0D4] rounded-lg"
                />
                <button
                  type="button"
                  onClick={handleAddFbPage}
                  className="px-3 py-2 rounded-lg bg-[#1877F2] text-white text-xs font-bold flex items-center gap-1"
                >
                  <Plus className="w-4 h-4" /> Add Page
                </button>
              </div>

              {fbPages.map((pg) => (
                <div
                  key={pg.id}
                  className={`rounded-xl p-3 border space-y-2 ${
                    pg.isActive ? 'bg-blue-50 border-[#1877F2]' : 'bg-[#F0F2F5] border-[#CED0D4]'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-[#050505]">{pg.pageName}</span>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handleSetActivePage(pg.id)}
                        className={`px-2.5 py-1 rounded-full text-[11px] font-bold ${
                          pg.isActive
                            ? 'bg-[#42B72A] text-white'
                            : 'bg-white border border-[#CED0D4] text-[#050505]'
                        }`}
                      >
                        {pg.isActive ? 'Active Page ✅' : 'Set Active'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeletePage(pg.id)}
                        className="p-1 rounded-lg bg-white border border-rose-200 text-rose-700"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={pg.pageId}
                      onChange={(e) => handleUpdatePageField(pg.id, 'pageId', e.target.value)}
                      placeholder="Facebook Page ID"
                      className="flex-1 px-2.5 py-1.5 text-xs bg-white border border-[#CED0D4] rounded-lg"
                    />
                    <button
                      type="button"
                      onClick={() => handleSaveFbPages(`${pg.pageName} Page ID save ho gaya!`)}
                      className="px-3 py-1.5 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                    >
                      Save ID
                    </button>
                  </div>

                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={pg.pageAccessToken}
                      onChange={(e) => handleUpdatePageField(pg.id, 'pageAccessToken', e.target.value)}
                      placeholder="Facebook Page Access Token"
                      className="flex-1 px-2.5 py-1.5 text-xs bg-white border border-[#CED0D4] rounded-lg"
                    />
                    <button
                      type="button"
                      onClick={() => handleSaveFbPages(`${pg.pageName} Page Token save ho gaya!`)}
                      className="px-3 py-1.5 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
                    >
                      Save Token
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Best Researched Schedule Card */}
            <div className="bg-white border border-[#CED0D4] rounded-xl p-3.5 space-y-3">
              <h3 className="text-sm font-bold text-[#050505]">
                7. Best Time Schedule (IST Locked)
              </h3>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] font-bold text-[#65676B]">Morning Reel (IST)</label>
                  <input
                    type="time"
                    value={schedule.morningReelIst}
                    onChange={(e) => setSchedule({ ...schedule, morningReelIst: e.target.value })}
                    className="w-full mt-1 px-2.5 py-1.5 bg-[#F0F2F5] border border-[#CED0D4] rounded-lg text-xs font-bold"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-bold text-[#65676B]">Evening Reel (IST)</label>
                  <input
                    type="time"
                    value={schedule.eveningReelIst}
                    onChange={(e) => setSchedule({ ...schedule, eveningReelIst: e.target.value })}
                    className="w-full mt-1 px-2.5 py-1.5 bg-[#F0F2F5] border border-[#CED0D4] rounded-lg text-xs font-bold"
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={handleSaveSchedule}
                className="w-full py-2 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
              >
                Save Schedule
              </button>
            </div>

            {/* Master Sync to GitHub Button */}
            <button
              type="button"
              disabled={busy}
              onClick={handleSyncToGitHub}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-[#42B72A] text-white text-sm font-extrabold"
            >
              <CloudUpload className="w-5 h-5" />
              {busy ? 'Syncing to GitHub...' : 'Sync All Keys & Config to GitHub'}
            </button>
          </>
        )}
      </main>

      {/* Fixed Facebook-Style Bottom Navigation Bar */}
      <nav className="fixed bottom-0 left-0 right-0 z-30 bg-white border-t border-[#CED0D4] px-2 py-1.5">
        <div className="max-w-xl mx-auto grid grid-cols-4 gap-1">
          {[
            { key: 'feed' as TabKey, label: 'Feed', Icon: Film },
            { key: 'reach' as TabKey, label: 'Reach & Photo', Icon: BarChart3 },
            { key: 'channels' as TabKey, label: 'Channels', Icon: Tv },
            { key: 'vault' as TabKey, label: 'Vault', Icon: KeyRound },
          ].map(({ key, label, Icon }) => {
            const active = tab === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`flex flex-col items-center justify-center py-1.5 rounded-lg text-[11px] font-bold ${
                  active ? 'text-[#1877F2] bg-blue-50' : 'text-[#65676B]'
                }`}
              >
                <Icon className="w-4 h-4 mb-0.5" />
                {label}
              </button>
            );
          })}
        </div>
      </nav>

      <VideoModal
        reel={activeVideo}
        onClose={() => setActiveVideo(null)}
        onSaveToPhone={handleSavePhone}
        onShare={shareReelFallback}
      />
    </div>
  );
}
