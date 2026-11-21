import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadProjectFonts } from '../../fonts';
import { SharedLottieSticker, resolveLottieStem } from '../../components/SharedLottieSticker';
import { VlogStickerProps } from './types';

loadProjectFonts();

export const VlogStickerOverlay: React.FC<VlogStickerProps> = ({
  emoji = '✨',
  label = 'KHOẢNH KHẮC',
  sublabel = '',
  position = 'top-right',
  accentColor = '#F59E0B',
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const isLandscape = width > height;

  const enter = spring({ frame, fps, config: { damping: 12, stiffness: 150 } });
  const exit = interpolate(
    frame,
    [Math.max(12, durationInFrames - 14), durationInFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const bobY = Math.sin(frame * 0.14) * 5;
  const ringPulse = 1 + 0.08 * Math.sin(frame * 0.18);
  const lottieStem = resolveLottieStem(emoji, `${label} ${sublabel}`);
  const lottieSize = isLandscape ? 72 : 66;

  const posStyle: React.CSSProperties =
    position === 'top-left'
      ? { top: isLandscape ? 54 : 110, left: isLandscape ? 60 : 40 }
      : position === 'bottom-right'
        ? { bottom: isLandscape ? 145 : 270, right: isLandscape ? 60 : 40 }
        : { top: isLandscape ? 54 : 110, right: isLandscape ? 60 : 40 };

  const slideFromX = position === 'top-left' ? -48 : 48;

  return (
    <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          ...posStyle,
          transform: `translateX(${interpolate(enter, [0, 1], [slideFromX, 0])}px) translateY(${bobY}px) scale(${interpolate(
            enter,
            [0, 1],
            [0.82, 1]
          )})`,
          opacity: enter * exit,
          display: 'flex',
          alignItems: 'center',
          gap: isLandscape ? 14 : 12,
          padding: isLandscape ? '12px 22px 12px 14px' : '10px 18px 10px 12px',
          borderRadius: 999,
          background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.84), rgba(30, 41, 59, 0.78))',
          border: `2px solid ${accentColor}`,
          boxShadow: `0 14px 36px rgba(0,0,0,0.48), 0 0 22px ${accentColor}33`,
        }}
      >
        <div
          style={{
            position: 'relative',
            width: lottieSize,
            height: lottieSize,
            borderRadius: 999,
            backgroundColor: `${accentColor}26`,
            border: `2px solid ${accentColor}99`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: `scale(${ringPulse})`,
            flexShrink: 0,
          }}
        >
          <SharedLottieSticker stem={lottieStem} size={lottieSize - 8} startFrame={0} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span
            style={{
              fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
              fontWeight: 800,
              fontSize: isLandscape ? 21 : 20,
              color: '#FFFFFF',
              letterSpacing: 0.4,
              lineHeight: 1.15,
              whiteSpace: 'nowrap',
            }}
          >
            {label}
          </span>
          {sublabel ? (
            <span
              style={{
                fontFamily: "'Quicksand', 'Nunito', sans-serif",
                fontWeight: 700,
                fontSize: isLandscape ? 14 : 13,
                color: accentColor,
                lineHeight: 1.1,
                whiteSpace: 'nowrap',
              }}
            >
              {sublabel}
            </span>
          ) : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};
