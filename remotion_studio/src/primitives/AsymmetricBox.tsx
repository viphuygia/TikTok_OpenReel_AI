import React from 'react';
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

/**
 * Asymmetric motion wrapper: snappy spring entrance (9-11 frames) and a 40% faster
 * ease-in exit (5-6 frames) so overlays feel crisp and never linger.
 */
export const AsymmetricBox: React.FC<{
  totalFrames: number;
  enterOffsetY?: number;
  exitOffsetY?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ totalFrames, enterOffsetY = 34, exitOffsetY = -28, style, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const safeTotal = Math.max(18, totalFrames);
  const exitFrames = 6;
  const exitStart = Math.max(10, safeTotal - exitFrames);

  const enterSpring = spring({
    frame,
    fps,
    config: { damping: 13, stiffness: 210, mass: 0.68 },
  });

  const exitProgress =
    frame >= exitStart
      ? interpolate(frame, [exitStart, safeTotal], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: Easing.in(Easing.cubic),
        })
      : 0;

  const opacity =
    interpolate(enterSpring, [0, 0.35, 1], [0, 1, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    }) *
    (1 - exitProgress);

  const scale =
    interpolate(enterSpring, [0, 1], [0.84, 1]) *
    interpolate(exitProgress, [0, 1], [1, 0.92]);

  const ty =
    interpolate(enterSpring, [0, 1], [enterOffsetY, 0]) +
    interpolate(exitProgress, [0, 1], [0, exitOffsetY]);

  return (
    <div
      style={{
        opacity,
        transform: `translate3d(0, ${ty}px, 0) scale(${scale})`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
