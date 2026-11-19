export type VlogIntroProps = {
  title: string;
  subtitle: string;
  badgeText?: string;
  accentColor?: string;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export type VlogChapterProps = {
  chapterNumber: string;
  title: string;
  subtitle?: string;
  accentColor?: string;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};

export type VlogOutroProps = {
  title: string;
  subtitle: string;
  ctaText: string;
  channelName?: string;
  accentColor?: string;
  durationSec?: number;
  width?: number;
  height?: number;
  aspectRatio?: '16:9' | '9:16';
};
