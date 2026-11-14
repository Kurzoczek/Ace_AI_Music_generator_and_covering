package com.acemusicgen.audio

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import java.io.File
import java.io.IOException
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Decodes any audio format the phone supports (MP3, AAC/M4A, FLAC, OGG/Opus, WAV...) to a 16-bit PCM WAV file
 * with the original sample rate and channel count. Python then resamples and analyzes it.
 * Works on content:// URIs from the system file picker - no storage permission is needed.
 */
object AudioDecoder {

    fun decodeToWav(context: Context, uri: Uri, out: File, isCancelled: () -> Boolean = { false }) {
        val extractor = MediaExtractor()
        extractor.setDataSource(context, uri, null)
        val track = (0 until extractor.trackCount).firstOrNull {
            extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
        } ?: throw IOException("no audio track")
        extractor.selectTrack(track)
        val inFormat = extractor.getTrackFormat(track)
        val codec = MediaCodec.createDecoderByType(inFormat.getString(MediaFormat.KEY_MIME)!!)
        codec.configure(inFormat, null, null, 0)
        codec.start()
        out.parentFile?.mkdirs()
        RandomAccessFile(out, "rw").use { raf ->
            raf.setLength(0)
            raf.write(ByteArray(44))                    // header written at the end
            var sampleRate = inFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
            var channels = inFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
            var floatPcm = false
            var dataBytes = 0L
            val info = MediaCodec.BufferInfo()
            var inputDone = false
            var outputDone = false
            val tmp = ByteArray(64 * 1024)
            try {
                while (!outputDone) {
                    if (isCancelled()) throw IOException("cancelled")
                    if (!inputDone) {
                        val inIdx = codec.dequeueInputBuffer(10_000)
                        if (inIdx >= 0) {
                            val buf = codec.getInputBuffer(inIdx)!!
                            val n = extractor.readSampleData(buf, 0)
                            if (n < 0) {
                                codec.queueInputBuffer(inIdx, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                                inputDone = true
                            } else {
                                codec.queueInputBuffer(inIdx, 0, n, extractor.sampleTime, 0)
                                extractor.advance()
                            }
                        }
                    }
                    val outIdx = codec.dequeueOutputBuffer(info, 10_000)
                    when {
                        outIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                            val f = codec.outputFormat
                            sampleRate = f.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                            channels = f.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                            floatPcm = f.containsKey(MediaFormat.KEY_PCM_ENCODING) &&
                                f.getInteger(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_FLOAT
                        }
                        outIdx >= 0 -> {
                            val buf = codec.getOutputBuffer(outIdx)!!
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            dataBytes += writePcm16(buf.slice().order(ByteOrder.LITTLE_ENDIAN), floatPcm, raf, tmp)
                            codec.releaseOutputBuffer(outIdx, false)
                            if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) outputDone = true
                        }
                    }
                }
            } finally {
                codec.stop()
                codec.release()
                extractor.release()
            }
            if (dataBytes == 0L) throw IOException("the file contains no decodable audio")
            raf.seek(0)
            raf.write(wavHeader(sampleRate, channels, dataBytes))
        }
    }

    private fun writePcm16(src: ByteBuffer, floatPcm: Boolean, raf: RandomAccessFile, tmp: ByteArray): Long {
        if (!floatPcm) {
            var written = 0L
            while (src.hasRemaining()) {
                val n = minOf(tmp.size, src.remaining())
                src.get(tmp, 0, n)
                raf.write(tmp, 0, n)
                written += n
            }
            return written
        }
        val fb = src.asFloatBuffer()
        val out = ByteBuffer.allocate(fb.remaining() * 2).order(ByteOrder.LITTLE_ENDIAN)
        while (fb.hasRemaining()) {
            out.putShort((fb.get().coerceIn(-1f, 1f) * 32767f).toInt().toShort())
        }
        raf.write(out.array(), 0, out.position())
        return out.position().toLong()
    }

    private fun wavHeader(sr: Int, ch: Int, dataBytes: Long): ByteArray {
        val b = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        val size = dataBytes.coerceAtMost(0xFFFFFFFFL - 36)
        b.put("RIFF".toByteArray()); b.putInt((36 + size).toInt()); b.put("WAVE".toByteArray())
        b.put("fmt ".toByteArray()); b.putInt(16); b.putShort(1); b.putShort(ch.toShort()); b.putInt(sr)
        b.putInt(sr * ch * 2); b.putShort((ch * 2).toShort()); b.putShort(16)
        b.put("data".toByteArray()); b.putInt(size.toInt())
        return b.array()
    }
}
