let context: AudioContext | undefined;
export function unlockSound() {
  try {
    context ??= new AudioContext();
    void context.resume().catch(() => {});
  } catch {
    /* Sound is optional. */
  }
}
export function chime() {
  if (!context || context.state !== 'running') return;
  const start = context.currentTime;
  [523.25, 659.25, 783.99].forEach((frequency, i) => {
    const oscillator = context!.createOscillator();
    const gain = context!.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start + i * 0.13);
    gain.gain.linearRampToValueAtTime(0.1, start + i * 0.13 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.001, start + i * 0.13 + 0.8);
    oscillator.connect(gain);
    gain.connect(context!.destination);
    oscillator.start(start + i * 0.13);
    oscillator.stop(start + i * 0.13 + 0.85);
    oscillator.onended = () => {
      oscillator.disconnect();
      gain.disconnect();
    };
  });
}
