#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# flake8: noqa
# pylint: disable=broad-exception-raised, raise-missing-from, too-many-arguments, redefined-outer-name
# pylint: disable=multiple-statements, logging-fstring-interpolation, trailing-whitespace, line-too-long
# pylint: disable=broad-exception-caught, missing-function-docstring, missing-class-docstring
# pylint: disable=f-string-without-interpolation, import-error
# pylance: disable=reportMissingImports, reportMissingModuleSource
# mypy: disable-error-code="import-untyped, import-not-found, attr-defined"

import urllib.parse
import subprocess
import tempfile
import os
import time
from flask import Flask, request, Response
from TeraTTS import TTS
from ruaccent import RUAccent
import logging
import dotenv

logger = logging.getLogger(__name__)

dotenv.load_dotenv()

# Configure logging early so INFO-level messages are visible
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s:%(funcName)s:%(lineno)d - %(message)s",
)


# Suppress HuggingFace tokenizers parallelism warnings
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.info("INFO: TOKENIZERS_PARALLELISM=false (suppress tokenizer parallelism warnings)")

logging.info("INFO: Initializing TTS Engine (TeraTTS GLaDOS2)...")

accentizer = RUAccent()
try:
    accentizer.load(omograph_model_size="turbo", use_dictionary=True)
    logging.info("INFO: RUAccent models loaded: omograph_model_size=turbo, use_dictionary=True")
except Exception as e:
    logging.info(f"RUAccent initialization error: {str(e)}")

try:
    MODEL_PATH = os.getenv("MODEL_PATH", "TeraTTS/glados2-g2p-vits")
    tts = TTS(MODEL_PATH, add_time_to_end=0.5, tokenizer_load_dict=False)
    logging.info(f"INFO: TTS model loaded from {MODEL_PATH}")
except Exception as e:
    raise RuntimeError(f"TTS model initialization error from {MODEL_PATH}: {str(e)}")

def preprocess_text(raw_text: str) -> str:
    """Apply accentization and text normalization for better synthesis quality."""
    try:
        return accentizer.process_all(raw_text)
    except Exception as e:
        logging.info(f"RUAccent processing error: {str(e)}; fallback to raw text")
        return raw_text

app = Flask(__name__)

@app.route('/synthesize/', defaults={'text': ''})
@app.route('/synthesize/<path:text>')
def synthesize(text):
    if text == '': return 'No input', 400

    request_start = time.perf_counter()
    line = urllib.parse.unquote(request.url[request.url.find('synthesize/') + 11:])
    
    try:
        accent_start = time.perf_counter()
        processed_text = preprocess_text(line)
        accent_duration = (time.perf_counter() - accent_start)*1000
        logging.info(f"synthesize: stage=accent; duration={accent_duration:.0f} ms")
        logging.info(f"Processed text: {processed_text}")
        if processed_text == "Не шм+огла": processed_text = "Не шмогл+а"
        text_len = len(processed_text)

        tts_start = time.perf_counter()
        audio = tts(processed_text, lenght_scale=2)
        tts_duration = (time.perf_counter() - tts_start)*1000
        logging.info(f"synthesize: stage=tts; duration={tts_duration:.0f} ms")
        
        # Create temporary files for WAV and MP3
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wav_file:
            wav_path = wav_file.name
        
        try:
            # Save WAV
            save_start = time.perf_counter()
            tts.save_wav(audio, wav_path)
            save_duration = time.perf_counter() - save_start
            logging.info(f"synthesize: stage=save_wav; duration={save_duration:.0f} ms")

            # Convert WAV → MP3 via FFmpeg
            mp3_path = wav_path.replace('.wav', '.mp3')
            cmd = [ 'ffmpeg', '-y', '-i', wav_path, '-codec:a', 'libmp3lame', '-q:a', '2', mp3_path ]
            ffmpeg_start = time.perf_counter()
            subprocess.run(cmd, check=True, capture_output=True)
            ffmpeg_duration = (time.perf_counter() - ffmpeg_start)*1000
            logging.info(f"synthesize: stage=ffmpeg; duration={ffmpeg_duration:.0f} ms")
            
            # Read MP3 and return
            with open(mp3_path, 'rb') as f:
                audio_data = f.read()
                
        finally:
            # Cleanup temporary files
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)
        
        response = Response(
            audio_data,
            mimetype='audio/mpeg',
            headers={'Content-Disposition': 'inline; filename="glados.mp3"'}
        )
        total_duration = time.perf_counter() - request_start
        total_per_char = total_duration / max(text_len, 1) * 1000
        logging.info(
            f"synthesize: total={total_duration:.3f} s; char={total_per_char:.0f} ms"
        )
        return response
        
    except subprocess.CalledProcessError as e:
        return f"FFmpeg conversion error: {str(e)}", 500
    except Exception as e:
        return f"TTS synthesis error: {str(e)}", 500

if __name__ == "__main__":
    logging.info("INFO: Initializing TTS Server (Flask)...")
    # Hide default Flask banner
    import sys as _sys
    cli = _sys.modules.get('flask.cli')
    if cli is not None:
        cli.show_server_banner = lambda *x: None
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8124")))
