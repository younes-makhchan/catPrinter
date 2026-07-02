(() => {
  const talkButton = document.querySelector('#talk-button');
  const serialConnect = document.querySelector('#serial-connect');
  const serialStatus = document.querySelector('#serial-status');
  const talkScreen = document.querySelector('#talk-screen');
  const stickerScreen = document.querySelector('#sticker-screen');
  const buttonLabel = document.querySelector('#button-label');
  const status = document.querySelector('#status');
  const heardPrompt = document.querySelector('#heard-prompt');
  const previewFrame = document.querySelector('#preview-frame');
  const preview = document.querySelector('#sticker-preview');
  const thinkingMark = document.querySelector('#thinking-mark');
  const printStatus = document.querySelector('#print-status');
  const emptyPreview = document.querySelector('.empty-preview');
  const emptyMessage = document.querySelector('#empty-message');
  const thinkingAudio = document.querySelector('#thinking-audio');
  const demoTextInput = document.querySelector('#demo-text');
  const thinkingMsInput = document.querySelector('#thinking-ms');
  const transcriptMsInput = document.querySelector('#transcript-ms');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  let recognition;
  let isBusy = false;
  let wasReleased = false;
  let heardWords = '';
  let thinkingStartedAt = 0;
  let serialPort;
  let serialReader;
  let serialWriter;
  let serialReadBuffer = '';
  let demoTranscriptTimer;
  let demoPrintStatus = '';

  const demoConfig = {
    text: 'six,seven',
    thinkingMs: 2000,
    transcriptMs: 1800,
  };

  function setStatus(message) { status.textContent = message; }
  function wait(milliseconds) { return new Promise((resolve) => setTimeout(resolve, milliseconds)); }
  function setSerialStatus(message) { serialStatus.textContent = message; }

  async function sendSerialLine(message) {
    if (!serialWriter) return;
    const data = new TextEncoder().encode(`${message}\n`);
    try {
      await serialWriter.write(data);
    } catch (error) {
      setSerialStatus(`ESP32 write failed: ${error.message}`);
    }
  }

  function clampNumber(value, fallback, min, max) {
    const parsed = Number.parseInt(value, 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.min(max, Math.max(min, parsed));
  }

  function readDemoConfig() {
    demoConfig.text = (demoTextInput.value || 'six,seven').trim().slice(0, 48);
    demoConfig.thinkingMs = clampNumber(thinkingMsInput.value, 2000, 250, 10000);
    demoConfig.transcriptMs = clampNumber(transcriptMsInput.value, 1800, 250, 10000);
    demoTextInput.value = demoConfig.text;
    thinkingMsInput.value = demoConfig.thinkingMs;
    transcriptMsInput.value = demoConfig.transcriptMs;
  }

  async function sendDemoConfig() {
    readDemoConfig();
    await sendSerialLine(`CFG_TEXT=${demoConfig.text}`);
    await sendSerialLine(`CFG_THINK_MS=${demoConfig.thinkingMs}`);
    await sendSerialLine(`CFG_TRANSCRIPT_MS=${demoConfig.transcriptMs}`);
  }

  function setBusy(busy) {
    isBusy = busy;
    talkButton.disabled = busy;
  }

  function showScreen() {
    talkScreen.hidden = false;
    stickerScreen.hidden = false;
  }

  function returnToTalk(message) {
    showScreen('talk');
    clearDemoTimers();
    stopThinkingSound();
    emptyMessage.textContent = 'Press to talk';
    showStage('empty');
    buttonLabel.textContent = 'Press to talk';
    setStatus(message);
  }

  function showStage(stage, prompt = '') {
    previewFrame.dataset.state = stage;
    emptyPreview.hidden = stage !== 'empty';
    thinkingMark.hidden = stage !== 'thinking';
    heardPrompt.hidden = stage !== 'transcript';
    preview.hidden = stage !== 'image';
    if (stage === 'transcript') heardPrompt.textContent = prompt;
  }

  function startThinkingSound() {
    if (!thinkingAudio) return;
    thinkingAudio.currentTime = 0;
    thinkingAudio.play().catch(() => {
      setStatus('Thinking...');
    });
  }

  function stopThinkingSound() {
    if (!thinkingAudio) return;
    thinkingAudio.pause();
    thinkingAudio.currentTime = 0;
  }

  function clearDemoTimers() {
    if (demoTranscriptTimer) {
      clearTimeout(demoTranscriptTimer);
      demoTranscriptTimer = undefined;
    }
  }

  function showHardwareListening() {
    if (isBusy) return;
    readDemoConfig();
    clearDemoTimers();
    stopThinkingSound();
    printStatus.textContent = '';
    emptyMessage.textContent = 'Listening...';
    talkButton.classList.add('listening');
    buttonLabel.textContent = 'Listening...';
    setStatus('ESP32 is listening.');
    showStage('empty');
  }

  function showHardwareThinking() {
    if (isBusy) return;
    readDemoConfig();
    clearDemoTimers();
    talkButton.classList.remove('listening');
    buttonLabel.textContent = 'Thinking...';
    setStatus('ESP32 is thinking.');
    thinkingStartedAt = performance.now();
    showScreen('sticker');
    showStage('thinking');
    startThinkingSound();
    demoTranscriptTimer = setTimeout(() => {
      showStage('transcript', demoConfig.text);
      setStatus(`ESP32 heard: ${demoConfig.text}`);
    }, demoConfig.thinkingMs);
  }

  async function printGeneratedSticker(jobId) {
    await sendSerialLine('PRINTING');
    const printed = await fetch(`/api/stickers/${jobId}/print`, { method: 'POST' });
    const printedData = await printed.json();
    if (!printed.ok) {
      await sendSerialLine(`PRINT_ERROR:${printedData.error || 'print failed'}`);
      throw new Error(printedData.error || 'The sticker could not print.');
    }
    await sendSerialLine('PRINT_OK');
    return printedData;
  }

  async function printDemoImage() {
    if (isBusy) return;
    setBusy(true);
    demoPrintStatus = 'Printing...';
    await sendSerialLine('PRINTING');

    try {
      const printed = await fetch('/api/demo/print', { method: 'POST' });
      const printedData = await printed.json();
      if (!printed.ok) throw new Error(printedData.error || 'The demo image could not print.');
      await sendSerialLine('PRINT_OK');
      demoPrintStatus = 'Printed';
    } catch (error) {
      await sendSerialLine(`PRINT_ERROR:${error.message}`);
      demoPrintStatus = error.message;
    } finally {
      if (!preview.hidden) printStatus.textContent = demoPrintStatus;
      setBusy(false);
      buttonLabel.textContent = 'Press to talk';
    }
  }

  function showHardwareImage() {
    clearDemoTimers();
    stopThinkingSound();
    preview.src = `/api/demo/image?t=${Date.now()}`;
    showStage('image');
    setStatus('ESP32 showed the image.');
    printStatus.textContent = demoPrintStatus || 'Printing...';
  }

  async function makeSticker(prompt) {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt || isBusy) return;

    setBusy(true);
    const thinkingElapsed = performance.now() - thinkingStartedAt;
    await wait(Math.max(0, demoConfig.thinkingMs - thinkingElapsed));
    stopThinkingSound();
    showStage('transcript', cleanPrompt);
    printStatus.textContent = '';
    setStatus('I heard you. Making your sticker…');

    try {
      // Let the browser paint the transcript before image generation begins.
      await new Promise(requestAnimationFrame);
      const generated = await fetch('/api/stickers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: cleanPrompt }),
      });
      const generatedData = await generated.json();
      if (!generated.ok) throw new Error(generatedData.error || 'Could not make the sticker.');

      preview.src = generatedData.image_url;
      showStage('image');
      setStatus('Your sticker is ready. Printing…');
      printStatus.textContent = 'Sending it to the printer…';
      await new Promise(requestAnimationFrame);

      await printGeneratedSticker(generatedData.job_id);

      setStatus('Done! Hold the button to make another.');
      printStatus.textContent = 'Printed';
    } catch (error) {
      showStage('transcript', cleanPrompt);
      setStatus('Something went wrong. Try again.');
      printStatus.textContent = error.message;
    } finally {
      setBusy(false);
      buttonLabel.textContent = 'Press to talk';
    }
  }

  function startListening(event) {
    event?.preventDefault();
    if (isBusy) return;
    if (!SpeechRecognition) {
      setStatus('Voice input is not available in this browser.');
      return;
    }

    heardWords = '';
    wasReleased = false;
    recognition = new SpeechRecognition();
    recognition.lang = navigator.language || 'en-US';
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.onresult = (event) => {
      heardWords = Array.from(event.results).map((result) => result[0].transcript).join(' ').trim();
    };
    recognition.onerror = (event) => {
      if (event.error !== 'aborted') setStatus('I could not hear that. Please try again.');
    };
    recognition.onend = () => {
      talkButton.classList.remove('listening');
      buttonLabel.textContent = 'Press to talk';
      recognition = undefined;
      if (wasReleased && heardWords) makeSticker(heardWords);
      else if (wasReleased) returnToTalk('I did not catch an idea. Press and try again.');
    };
    try {
      recognition.start();
      printStatus.textContent = '';
      emptyMessage.textContent = 'Listening…';
      showStage('empty');
      talkButton.classList.add('listening');
      buttonLabel.textContent = 'Listening…';
      setStatus('Listening… say what you want to make.');
      if (event) talkButton.setPointerCapture?.(event.pointerId);
    } catch (_) {
      setStatus('Voice input is busy. Please try again.');
    }
  }

  function stopListening(event) {
    event?.preventDefault();
    wasReleased = true;
    talkButton.classList.remove('listening');
    buttonLabel.textContent = 'Thinking…';
    setStatus('Thinking…');
    thinkingStartedAt = performance.now();
    showScreen('sticker');
    showStage('thinking');
    startThinkingSound();
    if (!recognition) {
      if (heardWords) makeSticker(heardWords);
      else returnToTalk('I did not catch an idea. Press and try again.');
      return;
    }
    recognition.stop();
  }

  async function handleSerialLine(line) {
    if (!line) return;
    setSerialStatus(`ESP32: ${line}`);

    if (line === 'START_LISTENING') {
      showHardwareListening();
    } else if (line === 'STOP_LISTENING') {
      showHardwareThinking();
    } else if (line === 'PRINT_DEMO') {
      printDemoImage();
    } else if (line === 'SHOW_IMAGE') {
      showHardwareImage();
    }
  }

  async function readSerialLoop() {
    const decoder = new TextDecoder();
    try {
      while (serialPort?.readable) {
        serialReader = serialPort.readable.getReader();
        try {
          while (true) {
            const { value, done } = await serialReader.read();
            if (done) break;
            serialReadBuffer += decoder.decode(value, { stream: true });
            const lines = serialReadBuffer.split(/\r?\n/);
            serialReadBuffer = lines.pop() || '';
            for (const line of lines) await handleSerialLine(line.trim());
          }
        } finally {
          serialReader.releaseLock();
          serialReader = undefined;
        }
      }
    } catch (error) {
      setSerialStatus(`ESP32 disconnected: ${error.message}`);
    }
  }

  async function connectSerial() {
    if (!('serial' in navigator)) {
      setSerialStatus('Web Serial needs Chrome or Edge on localhost/HTTPS.');
      return;
    }

    try {
      serialPort = await navigator.serial.requestPort();
      await serialPort.open({ baudRate: 115200 });
      serialWriter = serialPort.writable.getWriter();
      serialConnect.disabled = true;
      serialConnect.textContent = 'ESP32 connected';
      setSerialStatus('ESP32 connected');
      await sendDemoConfig();
      readSerialLoop();
    } catch (error) {
      setSerialStatus(`ESP32 connection failed: ${error.message}`);
    }
  }

  talkButton.addEventListener('pointerdown', startListening);
  talkButton.addEventListener('pointerup', stopListening);
  talkButton.addEventListener('pointercancel', stopListening);
  serialConnect.addEventListener('click', connectSerial);
  demoTextInput.addEventListener('change', sendDemoConfig);
  thinkingMsInput.addEventListener('change', sendDemoConfig);
  transcriptMsInput.addEventListener('change', sendDemoConfig);
})();
