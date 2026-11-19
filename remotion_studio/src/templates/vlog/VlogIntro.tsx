import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadProjectFonts } from '../../fonts';
import { VlogIntroProps } from './types';

loadProjectFonts();

export const VlogIntro: React.FC<VlogIntroProps> = ({
  title,
  subtitle,
  badgeText = 'OUTDOOR VLOG · 4K',
  accentColor = '#F59E0B',
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const isLandscape = width > height;

  const masterAlpha = interpolate(
    frame,
    [0, 14, Math.max(20, durationInFrames - 18), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const badgeSpring = spring({ frame: Math.max(0, frame - 4), fps, config: { damping: 14, stiffness: 120 } });
  const titleSpring = spring({ frame: Math.max(0, frame - 10), fps, config: { damping: 16, stiffness: 110 } });
  const subSpring = spring({ frame: Math.max(0, frame - 20), fps, config: { damping: 16, stiffness: 100 } });
  const lineWidthPct = interpolate(frame, [12, 42], [0, 100], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const shimmerX = interpolate(frame, [20, 68], [-40, 140], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const titleFontSize = isLandscape ? Math.round(width * 0.044) : Math.round(width * 0.068);
  const subFontSize = isLandscape ? Math.round(width * 0.017) : Math.round(width * 0.032);
  const badgeFontSize = isLandscape ? 20 : 24;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: 'transparent',
        opacity: masterAlpha,
        justifyContent: 'center',
        alignItems: 'center',
        padding: isLandscape ? '0 10%' : '0 8%',
      }}
    >
      {/* Subtle cinematic vignette scrim behind title so opening 4K clip stays vivid */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background:
            'radial-gradient(ellipse at center, rgba(6,10,18,0.58) 0%, rgba(6,10,18,0.28) 55%, rgba(6,10,18,0.08) 100%)',
        }}
      />

      <div
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          maxWidth: isLandscape ? '82%' : '92%',
        }}
      >
        {/* Top Badge */}
        <div
          style={{
            transform: `translateY(${interpolate(badgeSpring, [0, 1], [-24, 0])}px) scale(${interpolate(
              badgeSpring,
              [0, 1],
              [0.9, 1]
            )})`,
            opacity: badgeSpring,
            marginBottom: isLandscape ? 22 : 28,
            padding: '10px 24px',
            borderRadius: 999,
            backgroundColor: 'rgba(15, 23, 42, 0.72)',
            border: `2px solid ${accentColor}`,
            boxShadow: `0 10px 30px rgba(0,0,0,0.45)`,
            color: '#F8FAFC',
            fontFamily: "'Montserrat Black', 'Be Vietnam Pro', sans-serif",
            fontSize: badgeFontSize,
            letterSpacing: 3,
            textTransform: 'uppercase',
          }}
        >
          {badgeText}
        </div>

        {/* Main Cinematic Title */}
        <div
          style={{
            position: 'relative',
            overflow: 'hidden',
            transform: `translateY(${interpolate(titleSpring, [0, 1], [34, 0])}px)`,
            opacity: titleSpring,
            fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
            fontWeight: 900,
            fontSize: titleFontSize,
            lineHeight: 1.18,
            color: '#FFFFFF',
            textShadow: '0 8px 34px rgba(0,0,0,0.85), 0 2px 8px rgba(0,0,0,0.9)',
            padding: '4px 12px',
          }}
        >
          {title}
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${shimmerX}%`,
              width: '28%',
              background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.28), transparent)',
              transform: 'skewX(-18deg)',
              pointerEvents: 'none',
            }}
          />
        </div>

        {/* Animated Accent Underline Wipe */}
        <div
          style={{
            marginTop: 18,
            marginBottom: 18,
            width: isLandscape ? 320 : 240,
            height: 5,
            borderRadius: 999,
            backgroundColor: 'rgba(255,255,255,0.18)',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${lineWidthPct}%`,
              height: '100%',
              backgroundColor: accentColor,
              boxShadow: `0 0 18px ${accentColor}`,
            }}
          />
        </div>

        {/* Subtitle */}
        {subtitle ? (
          <div
            style={{
              transform: `translateY(${interpolate(subSpring, [0, 1], [18, 0])}px)`,
              opacity: subSpring,
              fontFamily: "'Quicksand', 'Nunito', sans-serif",
              fontWeight: 700,
              fontSize: subFontSize,
              color: '#E2E8F0',
              textShadow: '0 4px 18px rgba(0,0,0,0.9)',
              letterSpacing: 0.6,
            }}
          >
            {subtitle}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
