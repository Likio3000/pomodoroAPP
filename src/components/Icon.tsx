export type IconName =
  | 'play'
  | 'pause'
  | 'reset'
  | 'settings'
  | 'plus'
  | 'check'
  | 'close'
  | 'trash'
  | 'download'
  | 'arrow'
  | 'edit'
  | 'sound';
const paths: Record<IconName, string> = {
  play: 'm8 5 11 7-11 7Z',
  pause: 'M8 5v14M16 5v14',
  reset: 'M20 7v5h-5M20 12a8 8 0 1 0-2.5 5.8',
  settings:
    'm9 3-1 3-3 1-2 3 2 2-1 3 3 2 2-1 3 2 3-2 2 1 3-3-1-3 1-3-3-2-1-3Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  plus: 'M12 5v14M5 12h14',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12M6 18 18 6',
  trash: 'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7',
  download: 'M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  edit: 'm14 4 6 6M3 21l5-1L21 7l-5-5L3 15Z',
  sound: 'M11 4 5 9H2v6h3l6 5ZM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14',
};
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={name === 'play' ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
