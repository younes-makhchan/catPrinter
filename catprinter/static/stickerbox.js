(() => {
  const talkButton = document.querySelector('#talk-button');
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
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  let recognition;
  let isBusy = false;
  let wasReleased = false;
  let heardWords = '';
  let thinkingStartedAt = 0;

  function setStatus(message) { status.textContent = message; }
  function wait(milliseconds) { return new Promise((resolve) => setTimeout(resolve, milliseconds)); }

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

  async function makeSticker(prompt) {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt || isBusy) return;

    setBusy(true);
    const thinkingElapsed = performance.now() - thinkingStartedAt;
    await wait(Math.max(0, 2000 - thinkingElapsed));
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

      const printed = await fetch(`/api/stickers/${generatedData.job_id}/print`, { method: 'POST' });
      const printedData = await printed.json();
      if (!printed.ok) throw new Error(printedData.error || 'The sticker could not print.');

      setStatus('Done! Hold the button to make another.');
      printStatus.textContent = 'Printed ✦';
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
    event.preventDefault();
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
      talkButton.setPointerCapture?.(event.pointerId);
    } catch (_) {
      setStatus('Voice input is busy. Please try again.');
    }
  }

  function stopListening(event) {
    event.preventDefault();
    wasReleased = true;
    talkButton.classList.remove('listening');
    buttonLabel.textContent = 'Thinking…';
    setStatus('Thinking…');
    thinkingStartedAt = performance.now();
    showScreen('sticker');
    showStage('thinking');
    if (!recognition) {
      if (heardWords) makeSticker(heardWords);
      else returnToTalk('I did not catch an idea. Press and try again.');
      return;
    }
    recognition.stop();
  }

  talkButton.addEventListener('pointerdown', startListening);
  talkButton.addEventListener('pointerup', stopListening);
  talkButton.addEventListener('pointercancel', stopListening);
})();
