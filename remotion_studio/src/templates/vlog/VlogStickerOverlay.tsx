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
  targetX = 56,
  targetY = 58,
  showArrow = true,
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

  if (variant === 'free_pop') {
    const popSize = isLandscape ? 142 : 118;
    const wiggle = Math.sin(frame * 0.16) * 5.5;
    const tx = Math.max(12, Math.min(88, Number(targetX ?? 56)));
    const ty = Math.max(16, Math.min(82, Number(targetY ?? 58)));
    const px = (tx / 100) * width;
    const py = (ty / 100) * height;
    const hasPtr = Boolean(showArrow);
    const sx = hasPtr
      ? Math.max(130, Math.min(width - 130, px + (tx > 52 ? (isLandscape ? -175 : -125) : (isLandscape ? 175 : 125))))
      : (isLeft ? (isLandscape ? 145 : 110) : width - (isLandscape ? 145 : 110));
    const sy = hasPtr
      ? Math.max(120, Math.min(height - 160, py + (ty > 52 ? (isLandscape ? -135 : -130) : (isLandscape ? 115 : 110))))
      : (position.includes('bottom') ? height - (isLandscape ? 210 : 320) : (isLandscape ? 145 : 195));

    return (
      <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none', opacity: exit }}>
        {hasPtr ? (
          <svg width={width} height={height} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
            <defs>
              <marker id="vlogFreeArrow" markerWidth="10" markerHeight="10" refX="7" refY="3.5" orient="auto">
                <polygon points="0 0, 8 3.5, 0 7" fill={accentColor} />
              </marker>
            </defs>
            <path
              d={`M ${sx} ${sy + 18} Q ${(sx + px) / 2} ${sy - 20} ${px} ${py}`}
              fill="none"
              stroke={accentColor}
              strokeWidth={isLandscape ? 4.5 : 3.8}
              strokeLinecap="round"
              markerEnd="url(#vlogFreeArrow)"
              opacity={enter}
              style={{ filter: `drop-shadow(0 0 8px ${accentColor})` }}
            />
            <circle
              cx={px}
              cy={py}
              r={(isLandscape ? 22 : 18) * ringPulse}
              fill={`${accentColor}26`}
              stroke={accentColor}
              strokeWidth={2}
              opacity={enter}
            />
          </svg>
        ) : null}
        <div
          style={{
            position: 'absolute',
            left: sx,
            top: sy,
            transform: `translate(-50%, -50%) translateY(${bobY * 1.3}px) rotate(${wiggle}deg) scale(${interpolate(enter, [0, 1], [0.35, 1])})`,
            opacity: enter,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <div
            style={{
              filter: `drop-shadow(0 14px 26px rgba(0,0,0,0.52)) drop-shadow(0 0 18px ${accentColor}66)`,
            }}
          >
            <SharedLottieSticker stem={lottieStem} size={popSize} startFrame={0} />
          </div>
          {label ? (
            <span
              style={{
                fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                fontWeight: 900,
                fontSize: isLandscape ? 21 : 19,
                color: '#FFFFFF',
                textShadow: `0 2px 10px rgba(0,0,0,0.95), 0 0 14px ${accentColor}99`,
                letterSpacing: 0.3,
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </span>
          ) : null}
        </div>
      </AbsoluteFill>
    );
  }

  if (variant === 'pointer') {
    const tx = Math.max(12, Math.min(88, Number(targetX ?? 56)));
    const ty = Math.max(16, Math.min(82, Number(targetY ?? 58)));
    const px = (tx / 100) * width;
    const py = (ty / 100) * height;
    const cardOnLeft = tx > 54;
    const cardAbove = ty > 54;
    const dx = cardOnLeft ? (isLandscape ? -195 : -135) : (isLandscape ? 195 : 135);
    const dy = cardAbove ? (isLandscape ? -145 : -140) : (isLandscape ? 125 : 120);
    const cx = Math.max(isLandscape ? 230 : 175, Math.min(width - (isLandscape ? 230 : 175), px + dx));
    const cy = Math.max(isLandscape ? 110 : 150, Math.min(height - (isLandscape ? 170 : 280), py + dy));
    const elbowX = px + (cx - px) * 0.42;
    const lineProg = interpolate(enter, [0, 1], [0, 1]);

    return (
      <AbsoluteFill style={{ backgroundColor: 'transparent', pointerEvents: 'none', opacity: exit }}>
        <svg width={width} height={height} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>
          <polyline
            points={`${px},${py} ${elbowX},${cy} ${cx},${cy}`}
            fill="none"
            stroke={accentColor}
            strokeWidth={isLandscape ? 4 : 3.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={600}
            strokeDashoffset={600 * (1 - lineProg)}
            style={{ filter: `drop-shadow(0 0 8px ${accentColor})` }}
          />
          <circle
            cx={px}
            cy={py}
            r={(isLandscape ? 26 : 22) * ringPulse}
            fill={`${accentColor}22`}
            stroke={accentColor}
            strokeWidth={2.5}
            opacity={enter}
          />
          <circle cx={px} cy={py} r={isLandscape ? 9 : 8} fill={accentColor} opacity={enter} />
        </svg>
        <div
          style={{
            position: 'absolute',
            left: cx,
            top: cy,
            transform: `translate(-50%, -50%) scale(${interpolate(enter, [0, 1], [0.78, 1])})`,
            opacity: enter,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: isLandscape ? '11px 20px 11px 14px' : '9px 16px 9px 11px',
            borderRadius: 16,
            background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.90), rgba(30, 41, 59, 0.85))',
            border: `2px solid ${accentColor}`,
            boxShadow: `0 16px 36px rgba(0,0,0,0.55), 0 0 20px ${accentColor}40`,
            maxWidth: isLandscape ? 420 : 340,
          }}
        >
          <SharedLottieSticker stem={lottieStem} size={isLandscape ? 58 : 50} startFrame={0} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span
              style={{
                fontFamily: "'Be Vietnam Pro', 'Baloo 2', sans-serif",
                fontWeight: 800,
                fontSize: isLandscape ? 20 : 18,
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
                  fontSize: isLandscape ? 14 : 13,
                  color: accentColor,
                  lineHeight: 1.2,
                }}
              >
                {sublabel}
              </span>
            ) : null}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

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
