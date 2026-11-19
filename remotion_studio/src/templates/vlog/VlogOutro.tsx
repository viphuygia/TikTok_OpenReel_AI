import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadProjectFonts } from '../../fonts';
import { VlogOutroProps } from './types';

loadProjectFonts();

export const VlogOutro: React.FC<VlogOutroProps> = ({
  title,
  subtitle,
  ctaText,
  channelName = 'VLOG JOURNAL',
  accentColor = '#F59E0B',
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const isLandscape = width > height;

  const bgFade = interpolate(
    frame,
    [0, 18, Math.max(24, durationInFrames - 12), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const headSpring = spring({ frame: Math.max(0, frame - 6), fps, config: { damping: 15, stiffness: 115 } });
  const subSpring = spring({ frame: Math.max(0, frame - 16), fps, config: { damping: 16, stiffness: 110 } });

  const pills = isLandscape
    ? ['👍 LIKE VIDEO', '💬 COMMENT CẢM NGHĨ', '🔔 SUBSCRIBE KÊNH']
    : ['❤️ THẢ TIM', '📌 LƯU VIDEO', '➕ FOLLOW KÊNH'];

  const titleSize = isLandscape ? Math.round(width * 0.036) : Math.round(width * 0.056);
  const subSize = isLandscape ? Math.round(width * 0.016) : Math.round(width * 0.029);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: 'transparent',
        opacity: bgFade,
        justifyContent: 'center',
        alignItems: 'center',
        padding: isLandscape ? '0 10%' : '0 8%',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(180deg, rgba(8,12,20,0.45) 0%, rgba(8,12,20,0.78) 55%, rgba(8,12,20,0.86) 100%)',
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
        <div
          style={{
            marginBottom: 18,
            padding: '7px 20px',
            borderRadius: 999,
            backgroundColor: 'rgba(255,255,255,0.10)',
            border: '1px solid rgba(255,255,255,0.22)',
            color: accentColor,
            fontFamily: "'Montserrat Black', sans-serif",
            fontSize: isLandscape ? 18 : 22,
            letterSpacing: 2.4,
            textTransform: 'uppercase',
            opacity: headSpring,
          }}
        >
          {channelName}
        </div>

        <div
          style={{
            transform: `translateY(${interpolate(headSpring, [0, 1], [28, 0])}px)`,
            opacity: headSpring,
            fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
            fontWeight: 900,
            fontSize: titleSize,
            lineHeight: 1.2,
            color: '#FFFFFF',
            textShadow: '0 8px 28px rgba(0,0,0,0.8)',
          }}
        >
          {title}
        </div>

        {subtitle ? (
          <div
            style={{
              marginTop: 14,
              transform: `translateY(${interpolate(subSpring, [0, 1], [18, 0])}px)`,
              opacity: subSpring,
              fontFamily: "'Quicksand', 'Nunito', sans-serif",
              fontWeight: 700,
              fontSize: subSize,
              color: '#CBD5E1',
              maxWidth: 960,
            }}
          >
            {subtitle}
          </div>
        ) : null}

        {ctaText ? (
          <div
            style={{
              marginTop: 16,
              opacity: subSpring,
              fontFamily: "'Be Vietnam Pro', sans-serif",
              fontWeight: 700,
              fontSize: isLandscape ? 22 : 26,
              color: accentColor,
            }}
          >
            {ctaText}
          </div>
        ) : null}

        <div
          style={{
            marginTop: 28,
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: isLandscape ? 18 : 14,
          }}
        >
          {pills.map((label, idx) => {
            const pSpring = spring({
              frame: Math.max(0, frame - (24 + idx * 6)),
              fps,
              config: { damping: 12, stiffness: 140 },
            });
            const pulse = 1 + 0.025 * Math.sin((frame - idx * 8) * 0.14);
            return (
              <div
                key={label}
                style={{
                  transform: `scale(${interpolate(pSpring, [0, 1], [0.75, 1]) * pulse})`,
                  opacity: pSpring,
                  padding: isLandscape ? '13px 26px' : '12px 22px',
                  borderRadius: 999,
                  backgroundColor: idx === pills.length - 1 ? accentColor : 'rgba(15, 23, 42, 0.85)',
                  color: idx === pills.length - 1 ? '#090D16' : '#FFFFFF',
                  border: idx === pills.length - 1 ? 'none' : '1.5px solid rgba(255,255,255,0.28)',
                  fontFamily: "'Montserrat Black', 'Be Vietnam Pro', sans-serif",
                  fontWeight: 900,
                  fontSize: isLandscape ? 20 : 22,
                  boxShadow: idx === pills.length - 1 ? `0 10px 28px ${accentColor}66` : '0 10px 24px rgba(0,0,0,0.4)',
                }}
              >
                {label}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
