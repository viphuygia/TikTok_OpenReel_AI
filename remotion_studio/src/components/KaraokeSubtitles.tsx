import React, { useMemo } from 'react';
import { spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { SubtitleCue, WordTimestamp } from '../types';

interface Props {
  words: WordTimestamp[];
  subtitleY: number;
  activeColor: string;
  fontHeading?: string;
  subtitleLang?: 'vi' | 'bilingual' | 'en';
  enSubtitles?: SubtitleCue[];
}

interface WordChunk {
  words: WordTimestamp[];
  start: number;
  end: number;
}

const buildWordChunks = (words: WordTimestamp[], maxWords = 4, maxChars = 22): WordChunk[] => {
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
      if (buf.length >= maxWords || curChars > maxChars || gap > 0.35) {
        flush();
      }
    }
    buf.push(w);
    if (/[.!?;]$/.test(w.word) && buf.length >= 2) {
      flush();
    }
  }
  flush();
  return chunks;
};

export const KaraokeSubtitles: React.FC<Props> = ({
  words,
  subtitleY,
  activeColor,
  fontHeading = 'Baloo 2',
  subtitleLang = 'vi',
  enSubtitles = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  const activeEnCue = useMemo(() => {
    if (subtitleLang !== 'bilingual' || !enSubtitles?.length) return null;
    return enSubtitles.find((c) => currentTime >= c.start - 0.1 && currentTime <= c.end + 0.15) || null;
  }, [subtitleLang, enSubtitles, currentTime]);

  const chunks = useMemo(() => buildWordChunks(words), [words]);

  const activeChunk = useMemo(() => {
    return chunks.find((c) => currentTime >= c.start - 0.08 && currentTime <= c.end + 0.14);
  }, [chunks, currentTime]);

  if (!activeChunk) {
    return null;
  }

  const chunkEnter = spring({
    frame: Math.max(0, Math.round((currentTime - activeChunk.start) * fps)),
    fps,
    config: { damping: 14, stiffness: 220, mass: 0.6 },
  });

  const textLen = activeChunk.words.map((w) => w.word).join(' ').length;
  const fontSize = textLen <= 18 ? 58 : textLen <= 24 ? 50 : 44;

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: `${subtitleY * 100}%`,
        transform: `translateY(-50%) scale(${0.92 + 0.08 * chunkEnter})`,
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        paddingLeft: 56,
        paddingRight: 88, // Safe zone margin away from right-side icons
        pointerEvents: 'none',
        zIndex: 35,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, maxWidth: 880 }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            alignItems: 'center',
            gap: '8px 14px',
            maxWidth: 880,
            backgroundColor: 'rgba(0, 0, 0, 0.28)',
            borderRadius: 20,
            padding: '10px 22px',
            backdropFilter: 'blur(2px)',
          }}
        >
          {activeChunk.words.map((w, idx) => {
            const isActive = currentTime >= w.start - 0.04 && currentTime <= w.end + 0.08;
            const isSpoken = currentTime > w.end + 0.08;
            return (
              <span
                key={`${idx}-${w.word}`}
                style={{
                  fontFamily: `"${fontHeading}", "Montserrat Black", sans-serif`,
                  fontWeight: 800,
                  fontSize,
                  lineHeight: 1.15,
                  color: isActive ? activeColor : isSpoken ? '#FFFFFF' : '#E2E8F0',
                  WebkitTextStroke: '9px #000000',
                  paintOrder: 'stroke fill',
                  filter: isActive
                    ? 'drop-shadow(0 0 12px rgba(255,229,0,0.45)) drop-shadow(0 4px 8px rgba(0,0,0,0.85))'
                    : 'drop-shadow(0 4px 8px rgba(0,0,0,0.85))',
                  transform: isActive ? 'scale(1.16) translateY(-3px)' : 'scale(1)',
                  transition: 'transform 80ms ease-out',
                  display: 'inline-block',
                }}
              >
                {w.word}
              </span>
            );
          })}
        </div>
        {activeEnCue ? (
          <div
            style={{
              backgroundColor: 'rgba(9, 13, 22, 0.80)',
              borderRadius: 10,
              padding: '4px 14px',
              fontFamily: `'Be Vietnam Pro', 'Montserrat', sans-serif`,
              fontWeight: 700,
              fontSize: 30,
              lineHeight: 1.25,
              color: '#FEF08A',
              textAlign: 'center',
              textShadow: '0 2px 6px rgba(0,0,0,0.9)',
            }}
          >
            {activeEnCue.text}
          </div>
        ) : null}
      </div>
    </div>
  );
};
