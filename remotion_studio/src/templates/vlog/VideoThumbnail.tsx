import React from 'react';
import { AbsoluteFill } from 'remotion';
import { loadProjectFonts } from '../../fonts';

loadProjectFonts();

export type VideoThumbnailProps = {
  title: string;
  subtitle?: string;
  badgeText?: string;
  bgImageDataUrl?: string;
  accentColor?: string;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export const VideoThumbnail: React.FC<VideoThumbnailProps> = ({
  title = 'KHOẢNH KHẮC ĐÁNG NHỚ',
  subtitle = '',
  badgeText = 'HIGHLIGHT',
  bgImageDataUrl = '',
  accentColor = '#F59E0B',
  aspectRatio = '16:9',
}) => {
  const isPortrait = aspectRatio === '9:16';

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#090D16',
        overflow: 'hidden',
        fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
      }}
    >
      {bgImageDataUrl ? (
        <img
          src={bgImageDataUrl}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter: 'contrast(1.08) saturate(1.12) brightness(0.92)',
          }}
        />
      ) : null}

      {/* Smooth vignette & readability gradient */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: isPortrait
            ? 'linear-gradient(180deg, rgba(9,13,22,0.45) 0%, rgba(9,13,22,0.10) 35%, rgba(9,13,22,0.86) 82%, rgba(9,13,22,0.96) 100%)'
            : 'linear-gradient(90deg, rgba(9,13,22,0.92) 0%, rgba(9,13,22,0.68) 46%, rgba(9,13,22,0.18) 100%)',
        }}
      />

      {/* Accent border frame */}
      <div
        style={{
          position: 'absolute',
          inset: isPortrait ? 24 : 20,
          borderRadius: 24,
          border: `3px solid ${accentColor}AA`,
          boxShadow: `inset 0 0 36px ${accentColor}26`,
          pointerEvents: 'none',
        }}
      />

      {/* Main Title & Badge Block */}
      <div
        style={{
          position: 'absolute',
          left: isPortrait ? 56 : 72,
          right: isPortrait ? 56 : '34%',
          bottom: isPortrait ? 130 : undefined,
          top: isPortrait ? undefined : '50%',
          transform: isPortrait ? undefined : 'translateY(-50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          gap: isPortrait ? 22 : 18,
        }}
      >
        {badgeText ? (
          <div
            style={{
              padding: isPortrait ? '10px 24px' : '8px 20px',
              borderRadius: 999,
              backgroundColor: accentColor,
              color: '#090D16',
              fontWeight: 900,
              fontSize: isPortrait ? 28 : 22,
              letterSpacing: 1.4,
              textTransform: 'uppercase',
              boxShadow: `0 10px 26px ${accentColor}66`,
            }}
          >
            {badgeText}
          </div>
        ) : null}

        <div
          style={{
            fontWeight: 900,
            fontSize: isPortrait ? 78 : 74,
            lineHeight: 1.08,
            color: '#FFFFFF',
            textShadow: '0 6px 24px rgba(0,0,0,0.85), 0 2px 6px rgba(0,0,0,0.95)',
            wordBreak: 'break-word',
          }}
        >
          {title}
        </div>

        {subtitle ? (
          <div
            style={{
              fontFamily: "'Quicksand', 'Nunito', sans-serif",
              fontWeight: 700,
              fontSize: isPortrait ? 34 : 30,
              lineHeight: 1.3,
              color: '#F1F5F9',
              backgroundColor: 'rgba(15, 23, 42, 0.72)',
              borderLeft: `6px solid ${accentColor}`,
              padding: isPortrait ? '12px 22px' : '10px 18px',
              borderRadius: 12,
              maxWidth: '100%',
            }}
          >
            {subtitle}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
