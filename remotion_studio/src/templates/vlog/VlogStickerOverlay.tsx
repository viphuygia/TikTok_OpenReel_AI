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
  variant = 'pill',
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
        : position === 'bottom-left'
          ? { bottom: isLandscape ? 145 : 270, left: isLandscape ? 60 : 40 }
          : position === 'center-left'
            ? { top: isLandscape ? '38%' : '32%', left: isLandscape ? 64 : 40 }
            : position === 'center-right'
              ? { top: isLandscape ? '38%' : '32%', right: isLandscape ? 64 : 40 }
              : { top: isLandscape ? 54 : 110, right: isLandscape ? 60 : 40 };

  const isLeft = position.includes('left');
  const slideFromX = isLeft ? -48 : 48;

  if (variant === 'callout') {
    const lineScale = interpolate(enter, [0, 1], [0.1, 1]);
    return (
      <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none' }}>
        <div
          style={{
            position: 'absolute',
            ...posStyle,
            transform: `translateX(${interpolate(enter, [0, 1], [slideFromX, 0])}px) scale(${interpolate(enter, [0, 1], [0.88, 1])})`,
            opacity: enter * exit,
            display: 'flex',
            flexDirection: isLeft ? 'row' : 'row-reverse',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: 999,
              backgroundColor: accentColor,
              boxShadow: `0 0 0 6px ${accentColor}38, 0 0 18px ${accentColor}`,
              transform: `scale(${ringPulse})`,
              flexShrink: 0,
            }}
          />
          <div
            style={{
              width: isLandscape ? 38 : 26,
              height: 3,
              backgroundColor: accentColor,
              transform: `scaleX(${lineScale})`,
              transformOrigin: isLeft ? 'left center' : 'right center',
              flexShrink: 0,
            }}
          />
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: isLandscape ? '12px 20px' : '10px 16px',
              borderRadius: 14,
              background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.88), rgba(17, 24, 39, 0.82))',
              border: `1.5px solid ${accentColor}`,
              boxShadow: `0 16px 34px rgba(0,0,0,0.52)`,
              maxWidth: isLandscape ? 520 : 420,
            }}
          >
            <SharedLottieSticker stem={lottieStem} size={isLandscape ? 52 : 46} startFrame={0} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <span
                style={{
                  fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                  fontWeight: 800,
                  fontSize: isLandscape ? 21 : 19,
                  color: '#FFFFFF',
                  lineHeight: 1.2,
                }}
              >
                {label}
              </span>
              {sublabel ? (
                <span
                  style={{
                    fontFamily: "'Quicksand', 'Nunito', sans-serif",
                    fontWeight: 600,
                    fontSize: isLandscape ? 15 : 14,
                    color: '#E2E8F0',
                    lineHeight: 1.25,
                  }}
                >
                  {sublabel}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  if (variant === 'lower_third') {
    const ltPos: React.CSSProperties = isLeft
      ? { bottom: isLandscape ? 155 : 285, left: isLandscape ? 64 : 38 }
      : { bottom: isLandscape ? 155 : 285, right: isLandscape ? 64 : 38 };
    return (
      <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none' }}>
        <div
          style={{
            position: 'absolute',
            ...ltPos,
            transform: `translateY(${interpolate(enter, [0, 1], [36, 0])}px)`,
            opacity: enter * exit,
            display: 'flex',
            alignItems: 'stretch',
            gap: 14,
            padding: isLandscape ? '14px 24px 14px 18px' : '12px 18px 12px 14px',
            borderRadius: 16,
            background: 'linear-gradient(90deg, rgba(9, 14, 28, 0.90), rgba(15, 23, 42, 0.78))',
            border: '1px solid rgba(255,255,255,0.14)',
            boxShadow: '0 18px 42px rgba(0,0,0,0.55)',
            maxWidth: isLandscape ? 660 : 500,
          }}
        >
          <div
            style={{
              width: 5,
              borderRadius: 99,
              backgroundColor: accentColor,
              boxShadow: `0 0 14px ${accentColor}`,
              flexShrink: 0,
            }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SharedLottieSticker stem={lottieStem} size={isLandscape ? 54 : 48} startFrame={0} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <span
                style={{
                  fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                  fontWeight: 800,
                  fontSize: isLandscape ? 23 : 20,
                  color: '#FFFFFF',
                  lineHeight: 1.18,
                }}
              >
                {label}
              </span>
              {sublabel ? (
                <span
                  style={{
                    fontFamily: "'Quicksand', 'Nunito', sans-serif",
                    fontWeight: 700,
                    fontSize: isLandscape ? 15 : 14,
                    color: accentColor,
                    lineHeight: 1.22,
                  }}
                >
                  {sublabel}
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  if (variant === 'floating_lottie') {
    const bigSize = isLandscape ? 116 : 98;
    return (
      <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none' }}>
        <div
          style={{
            position: 'absolute',
            ...posStyle,
            transform: `translateY(${bobY * 1.4}px) scale(${interpolate(enter, [0, 1], [0.45, 1])})`,
            opacity: enter * exit,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <div
            style={{
              filter: `drop-shadow(0 12px 24px rgba(0,0,0,0.45)) drop-shadow(0 0 16px ${accentColor}55)`,
            }}
          >
            <SharedLottieSticker stem={lottieStem} size={bigSize} startFrame={0} />
          </div>
          {label ? (
            <div
              style={{
                padding: '6px 14px',
                borderRadius: 999,
                background: 'rgba(15, 23, 42, 0.84)',
                border: `1.5px solid ${accentColor}`,
                fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                fontWeight: 800,
                fontSize: isLandscape ? 16 : 15,
                color: '#FFFFFF',
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </div>
          ) : null}
        </div>
      </AbsoluteFill>
    );
  }

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
