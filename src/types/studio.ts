export type MoodCategory =
  | 'rangdari'
  | 'bewafai'
  | 'judai'
  | 'vafadari'
  | 'comedy';

export interface ApiVault {
  githubPat: string;
  githubRepo: string;
  groqApiKey: string;
  geminiApiKey: string;
  cloudflareAccountId: string;
  cloudflareApiToken: string;
}

export interface FacebookPageSlot {
  id: string;
  pageName: string;
  pageId: string;
  pageAccessToken: string;
  isActive: boolean;
  updatedAt: string;
}

export interface ResearchChannel {
  id: string;
  name: string;
  youtubeHandleOrUrl: string;
  category: MoodCategory;
  enabled: boolean;
}

export interface ScheduleConfig {
  morningReelIst: string;
  eveningReelIst: string;
  photoPostEnabled: boolean;
  photoPostDays: string[];
  photoPostIst: string;
  autoSaveToDevice: boolean;
}

export interface ReelResearchSource {
  channelName: string;
  videoTitle: string;
  videoUrl: string;
  viewsLabel: string;
}

export interface ReelStatusFlags {
  script: boolean;
  media: boolean;
  render: boolean;
  fbUpload: boolean;
  error?: string;
}

export interface ReachMetrics {
  views: number;
  likes: number;
  comments: number;
  shares: number;
}

export interface ReelHistoryItem {
  id: string;
  createdAt: string;
  slot: 'morning' | 'evening' | 'manual';
  mood: MoodCategory;
  title: string;
  scriptDialogue: string;
  caption: string;
  hashtags: string[];
  researchSource: ReelResearchSource;
  gapAnalysis: string[];
  status: ReelStatusFlags;
  videoDownloadUrl?: string;
  fbPostUrl?: string;
  reachMetrics?: ReachMetrics;
  savedLocally?: boolean;
}

export interface PhotoPostItem {
  id: string;
  createdAt: string;
  quoteText: string;
  caption: string;
  hashtags: string[];
  imageUrl?: string;
  fbPublished: boolean;
  fbPostUrl?: string;
  error?: string;
}

export interface CloudWorkflowStatus {
  state: 'idle' | 'queued' | 'in_progress' | 'completed';
  conclusion?: 'success' | 'failure' | 'cancelled' | string;
  runUrl?: string;
  updatedAt?: string;
  name?: string;
}
