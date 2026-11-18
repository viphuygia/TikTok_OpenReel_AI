import { Config } from '@remotion/cli/config';

// Offload Chromium compositing & H.264 video encoding to GPU when available
// and cap worker concurrency to avoid pinning CPU at 100%.
Config.setChromiumOpenGlRenderer('angle');
Config.setHardwareAcceleration('if-possible');
Config.setConcurrency(4);
