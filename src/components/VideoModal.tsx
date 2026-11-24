import React from 'react';
import { Download, Share2, X } from 'lucide-react';
import type { ReelHistoryItem } from '../types/studio';

interface Props {
  reel: ReelHistoryItem | null;
  onClose: () => void;
  onSaveToPhone: (reel: ReelHistoryItem) => void;
  onShare: (reel: ReelHistoryItem) => void;
}

export const VideoModal: React.FC<Props> = ({ reel, onClose, onSaveToPhone, onShare }) => {
  if (!reel) return null;

  return (
    <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-3 overflow-y-auto">
      <div className="w-full max-w-md bg-white border border-[#CED0D4] rounded-xl overflow-hidden my-4">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#CED0D4]">
          <div>
            <h3 className="text-sm font-bold text-[#050505] line-clamp-1">{reel.title}</h3>
            <p className="text-xs text-[#65676B] uppercase font-semibold">{reel.mood}</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full bg-[#F0F2F5] text-[#050505]"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-3 bg-[#F0F2F5] flex justify-center">
          {reel.videoDownloadUrl ? (
            <video
              src={reel.videoDownloadUrl}
              controls
              playsInline
              className="w-full max-h-[58vh] rounded-lg bg-black"
            />
          ) : (
            <div className="py-12 px-4 text-center text-sm text-[#65676B] bg-white border border-[#CED0D4] rounded-lg w-full">
              Video file abhi generate ho rahi hai ya URL uplabdh nahi hai.
            </div>
          )}
        </div>

        <div className="p-3 space-y-2 border-t border-[#CED0D4]">
          <p className="text-xs text-[#050505] whitespace-pre-line">{reel.caption}</p>
          <p className="text-xs font-medium text-[#1877F2]">{reel.hashtags.join(' ')}</p>
          <div className="flex gap-2 pt-2">
            <button
              onClick={() => onSaveToPhone(reel)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-[#1877F2] text-white text-xs font-bold"
            >
              <Download className="w-4 h-4" />
              Phone Me Save Karein
            </button>
            <button
              onClick={() => onShare(reel)}
              className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-[#42B72A] text-white text-xs font-bold"
            >
              <Share2 className="w-4 h-4" />
              1-Tap Share
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
