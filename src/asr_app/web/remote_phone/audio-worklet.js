class PcmResamplerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.frameSize = 640;
    this.ratio = sampleRate / this.targetRate;
    this.sourceBuffer = [];
    this.readIndex = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || input[0].length === 0) {
      return true;
    }

    const channelCount = input.length;
    const sampleCount = input[0].length;
    for (let i = 0; i < sampleCount; i += 1) {
      let mono = 0;
      for (let channel = 0; channel < channelCount; channel += 1) {
        mono += input[channel][i] || 0;
      }
      this.sourceBuffer.push(mono / channelCount);
    }

    while (this._canEmitFrame()) {
      const frame = new Int16Array(this.frameSize);
      for (let i = 0; i < this.frameSize; i += 1) {
        const position = this.readIndex + i * this.ratio;
        const leftIndex = Math.floor(position);
        const rightIndex = Math.min(leftIndex + 1, this.sourceBuffer.length - 1);
        const fraction = position - leftIndex;
        const sample = this.sourceBuffer[leftIndex] * (1 - fraction) + this.sourceBuffer[rightIndex] * fraction;
        const clamped = Math.max(-1, Math.min(1, sample));
        frame[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }

      this.readIndex += this.frameSize * this.ratio;
      const consumed = Math.floor(this.readIndex);
      if (consumed > 0) {
        this.sourceBuffer.splice(0, consumed);
        this.readIndex -= consumed;
      }
      this.port.postMessage(frame.buffer, [frame.buffer]);
    }

    return true;
  }

  _canEmitFrame() {
    const required = this.readIndex + (this.frameSize - 1) * this.ratio + 1;
    return this.sourceBuffer.length > required;
  }
}

registerProcessor("pcm-resampler", PcmResamplerProcessor);
