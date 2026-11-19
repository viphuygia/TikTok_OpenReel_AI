import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadProjectFonts } from '../../fonts';
import { VlogChapterProps } from './types';

loadProjectFonts();

export const VlogChapterCard: React.FC<VlogChapterProps> = ({
  chapterNumber,
  title,
  subtitle = '',
  accentColor = '#34D399',
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const isLandscape = width > height;

  const enter = spring({ frame, fps, config: { damping: 15, stiffness: 130 } });
  const exitAlpha = interpolate(
    frame,
    [Math.max(12, durationInFrames - 16), durationInFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );
  const exitSlideX = interpolate(
    frame,
    [Math.max(12, durationInFrames - 16), durationInFrames],
    [0, -48],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );
  const sweepPct = interpolate(frame, [6, Math.max(24, durationInFrames - 14)], [0, 100], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const numFontSize = isLandscape ? 38 : 34;
  const titleFontSize = isLandscape ? 30 : 28;
  const subFontSize = isLandscape ? 19 : 18;

  return (
    <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: isLandscape ? 64 : 44,
          bottom: isLandscape ? 130 : undefined,
          top: isLandscape ? undefined : 170,
          maxWidth: isLandscape ? '62%' : '86%',
          transform: `translateX(${interpolate(enter, [0, 1], [-56, 0]) + exitSlideX}px)`,
          opacity: enter * exitAlpha,
          display: 'flex',
          alignItems: 'stretch',
          borderRadius: 18,
          overflow: 'hidden',
          backgroundColor: 'rgba(10, 15, 28, 0.78)',
          border: '1px solid rgba(255, 255, 255, 0.16)',
          boxShadow: '0 18px 44px rgba(0, 0, 0, 0.52)',
        }}
      >
        {/* Spring accent bar */}
        <div
          style={{
            width: 8,
            backgroundColor: accentColor,
            boxShadow: `0 0 18px ${accentColor}`,
          }}
        />
        <div
          style={{
            padding: isLandscape ? '16px 28px 18px 22px' : '14px 22px 16px 18px',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span
              style={{
                fontFamily: "'Montserrat Black', sans-serif",
                fontSize: numFontSize,
                fontWeight: 900,
                color: accentColor,
                lineHeight: 1,
              }}
            >
              {chapterNumber}
            </span>
            <span
              style={{
                fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                fontSize: titleFontSize,
                fontWeight: 800,
                color: '#FFFFFF',
                textTransform: 'uppercase',
                letterSpacing: 0.8,
                lineHeight: 1.2,
              }}
            >
              {title}
            </span>
          </div>
          {subtitle ? (
            <div
              style={{
                fontFamily: "'Quicksand', 'Nunito', sans-serif",
                fontSize: subFontSize,
                fontWeight: 700,
                color: '#CBD5E1',
                paddingLeft: 2,
              }}
            >
              {subtitle}
            </div>
          ) : null}
          <div
            style={{
              marginTop: 6,
              height: 3,
              width: '100%',
              backgroundColor: 'rgba(255,255,255,0.14)',
              borderRadius: 999,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${sweepPct}%`,
                height: '100%',
                backgroundColor: accentColor,
              }}
            />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
