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
  titleStyle = 'cinematic_glass',
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const isLandscape = width > height;

  const styleMap = {
    cinematic_glass: {
      scrim: 'radial-gradient(ellipse at center, rgba(6,10,18,0.58) 0%, rgba(6,10,18,0.28) 55%, rgba(6,10,18,0.08) 100%)',
      cardBg: 'transparent',
      cardBorder: 'none',
      cardRadius: 0,
      badgeBg: 'rgba(15, 23, 42, 0.72)',
      badgeColor: '#F8FAFC',
      titleColor: '#FFFFFF',
      titleFont: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
      badgeRadius: 999,
    },
    editorial_minimal: {
      scrim: 'linear-gradient(180deg, rgba(10,14,22,0.45) 0%, rgba(10,14,22,0.18) 60%, rgba(10,14,22,0.45) 100%)',
      cardBg: 'rgba(255, 255, 255, 0.92)',
      cardBorder: `2px solid ${accentColor}`,
      cardRadius: 24,
      badgeBg: accentColor,
      badgeColor: '#0F172A',
      titleColor: '#0F172A',
      titleFont: "'Montserrat Black', 'Be Vietnam Pro', sans-serif",
      badgeRadius: 8,
    },
    campfire_warm: {
      scrim: 'radial-gradient(ellipse at center, rgba(28,16,8,0.62) 0%, rgba(18,10,5,0.28) 65%, rgba(0,0,0,0.08) 100%)',
      cardBg: 'rgba(28, 18, 11, 0.74)',
      cardBorder: `2px solid ${accentColor}`,
      cardRadius: 28,
      badgeBg: 'rgba(245, 158, 11, 0.22)',
      badgeColor: '#FDE68A',
      titleColor: '#FFFBEB',
      titleFont: "'Baloo 2', 'Be Vietnam Pro', sans-serif",
      badgeRadius: 999,
    },
    adventure_bold: {
      scrim: 'linear-gradient(135deg, rgba(6,18,30,0.64) 0%, rgba(15,23,42,0.30) 100%)',
      cardBg: 'rgba(12, 20, 36, 0.72)',
      cardBorder: `3px solid ${accentColor}`,
      cardRadius: 14,
      badgeBg: accentColor,
      badgeColor: '#090D16',
      titleColor: '#FFFFFF',
      titleFont: "'Montserrat Black', 'Be Vietnam Pro', sans-serif",
      badgeRadius: 6,
    },
    pastel_soft: {
      scrim: 'radial-gradient(ellipse at center, rgba(20,24,36,0.42) 0%, rgba(20,24,36,0.14) 70%, transparent 100%)',
      cardBg: 'rgba(248, 250, 252, 0.86)',
      cardBorder: `2px solid ${accentColor}`,
      cardRadius: 36,
      badgeBg: 'rgba(255,255,255,0.95)',
      badgeColor: '#1E293B',
      titleColor: '#1E293B',
      titleFont: "'Quicksand', 'Be Vietnam Pro', sans-serif",
      badgeRadius: 999,
    },
  } as const;
  const theme = styleMap[titleStyle] || styleMap.cinematic_glass;

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
          background: theme.scrim,
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
          backgroundColor: theme.cardBg,
          border: theme.cardBorder,
          borderRadius: theme.cardRadius,
          padding: theme.cardBg === 'transparent' ? 0 : isLandscape ? '34px 52px' : '28px 32px',
          boxShadow: theme.cardBg === 'transparent' ? 'none' : '0 24px 60px rgba(0,0,0,0.45)',
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
            borderRadius: theme.badgeRadius,
            backgroundColor: theme.badgeBg,
            border: `2px solid ${accentColor}`,
            boxShadow: `0 10px 30px rgba(0,0,0,0.35)`,
            color: theme.badgeColor,
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
            fontFamily: theme.titleFont,
            fontWeight: 900,
            fontSize: titleFontSize,
            lineHeight: 1.18,
            color: theme.titleColor,
            textShadow: theme.cardBg === 'transparent' ? '0 8px 34px rgba(0,0,0,0.85), 0 2px 8px rgba(0,0,0,0.9)' : 'none',
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
              color: theme.titleColor === '#FFFFFF' || theme.titleColor === '#FFFBEB' ? '#E2E8F0' : '#334155',
              textShadow: theme.cardBg === 'transparent' ? '0 4px 18px rgba(0,0,0,0.9)' : 'none',
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
