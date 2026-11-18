import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

/**
 * Delays child entrance by `delayFrames` so stacked HUD layers stagger naturally
 * instead of popping in on frame 0 simultaneously.
 */
export const StaggeredLayer: React.FC<{
  delayFrames?: number;
  offsetY?: number;
  offsetX?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ delayFrames = 0, offsetY = 24, offsetX = 0, style, children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = Math.max(0, frame - delayFrames);

  if (frame < delayFrames) {
    return null;
  }

  const prog = spring({
    frame: localFrame,
    fps,
    config: { damping: 14, stiffness: 190, mass: 0.72 },
  });

  const opacity = interpolate(prog, [0, 0.45, 1], [0, 0.9, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const tx = interpolate(prog, [0, 1], [offsetX, 0]);
  const ty = interpolate(prog, [0, 1], [offsetY, 0]);

  return (
    <div
      style={{
        opacity,
        transform: `translate3d(${tx}px, ${ty}px, 0)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
