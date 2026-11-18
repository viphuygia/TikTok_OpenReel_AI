import React from 'react';
import {
  AbsoluteFill,
  Loop,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { noise2D } from '@remotion/noise';
import { VideoClipItem } from '../types';

/**
 * Wraps <OffthreadVideo> with organic handheld drift (@remotion/noise) + punch-in
 * spring zoom so raw clips feel alive and cinematic rather than static.
 */
export const LivingVideoClip: React.FC<{
  clip: VideoClipItem;
  clipIdx: number;
  cameraIntensity?: 'subtle' | 'dynamic_ai' | 'energetic';
  colorFilter?: string;
  disableFlashShake?: boolean;
}> = ({ clip, clipIdx, cameraIntensity = 'dynamic_ai', colorFilter = 'none', disableFlashShake = true }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const totalFrames = Math.max(15, Math.round(clip.duration * fps));
  const mult = cameraIntensity === 'subtle' ? 0.65 : cameraIntensity === 'energetic' ? 1.45 : 1.05;

  const punch = disableFlashShake
    ? 0
    : spring({
        frame,
        fps,
        config: { damping: 12, stiffness: 210, mass: 0.65 },
      });

  // Smooth alternating zoom (even when disableFlashShake=true, alternate zoom-in / zoom-out + gentle 2.5px organic float)
  const isZoomOut = clip.zoomMode === 'zoom_out' || (clip.zoomMode !== 'punch_in' && clipIdx % 2 === 1);
  const driftZoom = disableFlashShake
    ? interpolate(frame, [0, totalFrames], isZoomOut ? [1.08, 1.01] : [1.0, 1.07], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
    : interpolate(frame, [0, totalFrames], isZoomOut ? [1.12 * mult, 1.01] : [1.02, 1.13 * mult], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
  const punchBoost = disableFlashShake
    ? 0
    : clip.zoomMode === 'punch_in' || clipIdx % 2 === 1
      ? interpolate(punch, [0, 1], [0.09 * mult, 0.015 * mult])
      : interpolate(punch, [0, 1], [0.0, 0.015 * mult]);

  // Organic handheld camera drift via @remotion/noise (gentle smooth float when disableFlashShake=true, stronger when false)
  const driftX = disableFlashShake
    ? noise2D('cam-x', frame * 0.012, clipIdx * 1.7) * 3.0
    : noise2D('cam-x', frame * 0.022, clipIdx * 1.7) * 10 * mult;
  const driftY = disableFlashShake
    ? noise2D('cam-y', frame * 0.012, clipIdx * 2.3) * 2.5
    : noise2D('cam-y', frame * 0.022, clipIdx * 2.3) * 8 * mult;
  const tiltDeg = disableFlashShake ? 0 : noise2D('cam-rot', frame * 0.018, clipIdx * 3.1) * 0.45 * mult;

  const flashOpacity =
    !disableFlashShake && clip.transitionType === 'flash' && frame < 6
      ? interpolate(frame, [0, 6], [0.55, 0], { extrapolateRight: 'clamp' })
      : 0;

  return (
    <AbsoluteFill style={{ overflow: 'hidden', backgroundColor: '#050810' }}>
      <Loop durationInFrames={totalFrames}>
        <OffthreadVideo
          src={staticFile(clip.src)}
          muted
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `translate3d(${driftX.toFixed(2)}px, ${driftY.toFixed(2)}px, 0) rotate(${tiltDeg.toFixed(3)}deg) scale(${(driftZoom + punchBoost).toFixed(4)})`,
            filter: colorFilter,
          }}
        />
      </Loop>
      {flashOpacity > 0 && (
        <AbsoluteFill
          style={{
            backgroundColor: '#FFFFFF',
            opacity: flashOpacity,
            pointerEvents: 'none',
          }}
        />
      )}
    </AbsoluteFill>
  );
};
