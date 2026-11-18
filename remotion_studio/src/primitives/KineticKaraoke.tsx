import React, { useMemo } from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { WordTimestamp } from '../types';

interface WordChunk {
  words: WordTimestamp[];
  start: number;
  end: number;
}

const buildSemanticChunks = (words: WordTimestamp[], maxWords = 5, maxChars = 28): WordChunk[] => {
  const chunks: WordChunk[] = [];
  let buf: WordTimestamp[] = [];

  const flush = () => {
    if (buf.length === 0) return;
    chunks.push({
      words: [...buf],
      start: buf[0].start,
      end: buf[buf.length - 1].end,
    });
    buf = [];
  };

  for (const w of words) {
    if (buf.length > 0) {
      const prevEnd = buf[buf.length - 1].end;
      const curChars = buf.reduce((acc, item) => acc + item.word.length + 1, 0) + w.word.length;
      const gap = w.start - prevEnd;
      if (buf.length >= maxWords || curChars > maxChars || gap > 0.28) {
        flush();
      }
    }
    buf.push(w);
    if (/[.!?;,]$/.test(w.word) && buf.length >= 2) {
      flush();
    }
  }
  flush();
  return chunks;
};

/**
 * Semantic Karaoke subtitles: groups 4-6 words by punctuation and natural pauses,
 * keeps line geometry locked (no padding/rotation jump) for effortless reading.
 */
export const KineticKaraoke: React.FC<{
  words: WordTimestamp[];
  subtitleY?: number;
  activeColor?: string;
  pillColor?: string;
  variant?: 'clean_stroke' | 'glass_pill' | 'accent_band';
  fontHeading?: string;
}> = ({
  words,
  subtitleY = 0.73,
  activeColor = '#FFE500',
  pillColor = '#E11D48',
  variant = 'clean_stroke',
  fontHeading = 'Baloo 2',
}) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const currentTime = frame / fps;

  const chunks = useMemo(() => buildSemanticChunks(words || []), [words]);
  if (chunks.length === 0) {
    return null;
  }

  const activeChunk = chunks.find((c) => currentTime >= c.start - 0.08 && currentTime <= c.end + 0.14);
  if (!activeChunk) {
    return null;
  }

  const chunkStartFrame = Math.floor(activeChunk.start * fps);
  const chunkEnter = spring({
    frame: Math.max(0, frame - chunkStartFrame),
    fps,
    config: { damping: 16, stiffness: 220, mass: 0.65 },
  });

  const topPx = Math.round(height * subtitleY);
  const containerBg =
    variant === 'glass_pill'
      ? 'rgba(15, 23, 42, 0.72)'
      : variant === 'accent_band'
        ? `${pillColor}D9`
        : 'transparent';

  return (
    <div
      style={{
        position: 'absolute',
        left: 48,
        right: 48,
        top: topPx,
        transform: `translateY(-50%) scale(${interpolate(chunkEnter, [0, 1], [0.95, 1]).toFixed(3)})`,
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'inline-flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          alignItems: 'center',
          gap: '8px 14px',
          padding: variant === 'clean_stroke' ? '0px' : '12px 24px',
          borderRadius: 20,
          background: containerBg,
          border: variant === 'glass_pill' ? '2px solid rgba(255,255,255,0.22)' : 'none',
          boxShadow: variant === 'clean_stroke' ? 'none' : '0 12px 30px rgba(0,0,0,0.45)',
        }}
      >
        {activeChunk.words.map((w, idx) => {
          const isActive = currentTime >= w.start - 0.03 && currentTime <= w.end + 0.09;
          const isPast = currentTime > w.end + 0.09;

          return (
            <span
              key={`${w.word}-${idx}`}
              style={{
                display: 'inline-block',
                fontFamily: `'${fontHeading}', 'Montserrat', sans-serif`,
                fontWeight: 900,
                fontSize: 54,
                lineHeight: 1.2,
                color: isActive ? activeColor : isPast ? '#FFFFFF' : 'rgba(255,255,255,0.88)',
                WebkitTextStroke: '9px #090D16',
                paintOrder: 'stroke fill',
                textShadow: isActive
                  ? `0 0 22px ${activeColor}99, 0 5px 12px rgba(0,0,0,0.92)`
                  : '0 5px 12px rgba(0,0,0,0.92)',
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
