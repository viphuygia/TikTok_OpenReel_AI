import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { CalloutItem } from '../types';

interface Props {
  item: CalloutItem;
  defaultY: number;
  fontHeading?: string;
}

const fitCalloutSize = (maxLineChars: number, base = 54): number => {
  if (maxLineChars <= 22) return base;
  if (maxLineChars <= 30) return Math.round(base * 0.86);
  if (maxLineChars <= 38) return Math.round(base * 0.74);
  return 34;
};

export const MulticolorCallout: React.FC<Props> = ({
  item,
  defaultY,
  fontHeading = 'Baloo 2',
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const startFrame = Math.round(item.start * fps);
  const endFrame = Math.round(item.end * fps);
  if (frame < startFrame || frame > endFrame) {
    return null;
  }

  const localFrame = frame - startFrame;
  const totalFrames = Math.max(10, endFrame - startFrame);

  const enterSpring = spring({
    frame: localFrame,
    fps,
    config: { damping: 13, stiffness: 190, mass: 0.75 },
  });

  const fadeOut = interpolate(
    localFrame,
    [Math.max(0, totalFrames - 8), totalFrames],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const yPos = item.y ?? defaultY;
  const maxLineLen = item.lines.reduce((acc, ln) => {
    const lineText = ln.tokens.map((t) => t.text).join(' ');
    return Math.max(acc, lineText.length);
  }, 10);

  const fontSize = item.fontSize ?? fitCalloutSize(maxLineLen, 54);
  const strokePx = Math.max(8, Math.round(fontSize * 0.19));

  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: `${yPos * 100}%`,
        transform: `translateY(${interpolate(enterSpring, [0, 1], [18, 0])}px) scale(${interpolate(enterSpring, [0, 1], [0.85, 1])})`,
        opacity: fadeOut,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        paddingLeft: 64,
        paddingRight: 88, // Safe zone margin avoiding right-side TikTok engagement icons
        pointerEvents: 'none',
        zIndex: 28,
      }}
    >
      {item.lines.map((line, li) => (
        <div
          key={li}
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'center',
            alignItems: 'center',
            textAlign: 'center',
            lineHeight: 1.24,
            marginBottom: li === 0 ? 4 : 0,
            maxWidth: 910,
          }}
        >
          {line.tokens.map((tok, ti) => (
            <span
              key={ti}
              style={{
                fontFamily: `"${fontHeading}", "Montserrat Black", sans-serif`,
                fontWeight: 800,
                fontSize,
                color: tok.color || '#FFFFFF',
                WebkitTextStroke: `${strokePx}px ${tok.strokeColor || '#000000'}`,
                paintOrder: 'stroke fill',
                filter: 'drop-shadow(0 3px 8px rgba(0,0,0,0.7))',
                marginRight: ti < line.tokens.length - 1 ? 12 : 0,
                whiteSpace: 'pre-wrap',
              }}
            >
              {tok.text}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
};
