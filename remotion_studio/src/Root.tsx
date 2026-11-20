import React from 'react';
import { Composition } from 'remotion';
import { TikTokComposition } from './TikTokComposition';
import { InnovationComposition } from './templates/innovation/InnovationComposition';
import { VlogIntro } from './templates/vlog/VlogIntro';
import { VlogChapterCard } from './templates/vlog/VlogChapterCard';
import { VlogOutro } from './templates/vlog/VlogOutro';
import { VlogStickerOverlay } from './templates/vlog/VlogStickerOverlay';
import { VlogIntroProps, VlogChapterProps, VlogOutroProps, VlogStickerProps } from './templates/vlog/types';
import { TikTokVideoProps } from './types';

const defaultProps: TikTokVideoProps = {
  title: 'TikTok Shop Review',
  durationSec: 25,
  badgeStyle: 'floral_plus_callouts',
  visualTheme: 'auto',
  layoutStyle: 'full',
  colorPreset: 'natural',
  creativeMode: 'breakthrough_ai',
  cameraIntensity: 'dynamic_ai',
  transparentBg: false,
  badgeOnly: false,
  hookY: 0.16,
  subtitleY: 0.72,
  fontHeading: 'Baloo 2',
  fontBrand: 'Montserrat Black',
  fontScript: 'Dancing Script',
  subtitleActiveColor: '#FFE500',
  floralBadge: {
    enabled: true,
    brand: 'Colgate',
    productLine: 'MaxFresh',
    category: 'nước súc miệng',
    brandColor: '#FFFFFF',
    productColor: '#38BDF8',
    categoryColor: '#FFF380',
    accentStrokeColor: '#BE185D',
    outerStrokeColor: '#FFFFFF',
    start: 0,
    end: 4.0,
    y: 0.16,
  },
  callouts: [],
  words: [],
  clips: [],
  bgmVolume: 0.14,
  sfxVolume: 0.55,
  sfxEvents: [],
};

export const RemotionRoot: React.FC = () => {
  const calcMeta = ({ props }: { props: Record<string, unknown> }) => {
    const fps = 30;
    const typed = props as unknown as TikTokVideoProps;
    const durationSec = Math.max(1.5, Number(typed.durationSec) || 25);
    const isLandscape = typed.aspectRatio === '16:9' || (Number(typed.width) > 0 && Number(typed.width) > Number(typed.height || 0));
    const width = Number(typed.width) || (isLandscape ? 1920 : 1080);
    const height = Number(typed.height) || (isLandscape ? 1080 : 1920);
    return {
      durationInFrames: Math.round(durationSec * fps),
      fps,
      width,
      height,
    };
  };

  const calcVlogMeta = ({ props }: { props: Record<string, unknown> }) => {
    const fps = 30;
    const typed = props as { durationSec?: number; width?: number; height?: number; aspectRatio?: string };
    const durationSec = Math.max(1.5, Number(typed.durationSec) || 4.5);
    const isPortrait = typed.aspectRatio === '9:16' || (Number(typed.height) > 0 && Number(typed.height) > Number(typed.width || 0));
    const width = Number(typed.width) || (isPortrait ? 1080 : 1920);
    const height = Number(typed.height) || (isPortrait ? 1920 : 1080);
    return {
      durationInFrames: Math.round(durationSec * fps),
      fps,
      width,
      height,
    };
  };

  const defaultVlogIntro: VlogIntroProps = {
    title: 'CHUYẾN ĐI ĐÁNG NHỚ',
    subtitle: 'Nhật ký hành trình & khoảnh khắc',
    badgeText: 'VLOG JOURNAL · 4K',
    accentColor: '#F59E0B',
    durationSec: 4.5,
    aspectRatio: '16:9',
  };
  const defaultVlogChapter: VlogChapterProps = {
    chapterNumber: '01',
    title: 'KHỞI HÀNH',
    subtitle: 'Những bước chuẩn bị đầu tiên',
    accentColor: '#34D399',
    durationSec: 3.5,
    aspectRatio: '16:9',
  };
  const defaultVlogOutro: VlogOutroProps = {
    title: 'CẢM ƠN BẠN ĐÃ ĐỒNG HÀNH!',
    subtitle: 'Hẹn gặp lại trong những hành trình tiếp theo',
    ctaText: 'Lưu lại cuối tuần đi thử nha!',
    channelName: 'VLOG JOURNAL',
    accentColor: '#F59E0B',
    durationSec: 6.0,
    aspectRatio: '16:9',
  };
  const defaultVlogSticker: VlogStickerProps = {
    emoji: '🔥',
    label: 'NHÓM LỬA TRẠI',
    sublabel: 'Khoảnh khắc ấm áp',
    position: 'top-right',
    accentColor: '#F59E0B',
    durationSec: 3.5,
    aspectRatio: '16:9',
  };

  return (
    <>
      <Composition
        id="TikTokVideo"
        component={TikTokComposition}
        durationInFrames={750}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
      <Composition
        id="TikTokInnovation"
        component={InnovationComposition}
        durationInFrames={750}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
      <Composition
        id="VlogIntro"
        component={VlogIntro}
        durationInFrames={135}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultVlogIntro}
        calculateMetadata={calcVlogMeta}
      />
      <Composition
        id="VlogChapterCard"
        component={VlogChapterCard}
        durationInFrames={105}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultVlogChapter}
        calculateMetadata={calcVlogMeta}
      />
      <Composition
        id="VlogOutro"
        component={VlogOutro}
        durationInFrames={180}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultVlogOutro}
        calculateMetadata={calcVlogMeta}
      />
      <Composition
        id="VlogStickerOverlay"
        component={VlogStickerOverlay}
        durationInFrames={105}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultVlogSticker}
        calculateMetadata={calcVlogMeta}
      />
    </>
  );
};
