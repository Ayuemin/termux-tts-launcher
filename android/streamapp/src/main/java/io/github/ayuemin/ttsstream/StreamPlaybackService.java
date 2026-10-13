package io.github.ayuemin.ttsstream;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;
import android.widget.Toast;

import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.SecureRandom;

/** Experimental progressive MP3 client. This app is independent of the stable launcher. */
public final class StreamPlaybackService extends Service {
    public static final String ACTION_TOGGLE = "io.github.ayuemin.ttsstream.TOGGLE";
    public static final String ACTION_STOP = "io.github.ayuemin.ttsstream.STOP";
    public static final String EXTRA_TEXT = "clipboard_text";
    private static final String CHANNEL_ID = "stream_playback";
    private static final int NOTIFICATION_ID = 1107;
    private static final String TAG = "TermuxTtsStream";
    private static final String SCRIPT = "/data/data/com.termux/files/usr/bin/tts-launcher-stream";
    private static final char[] HEX = "0123456789abcdef".toCharArray();

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final SecureRandom random = new SecureRandom();
    private boolean active;
    private int generation;
    private int port;
    private String token;
    private MediaPlayer player;

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager mgr = getSystemService(NotificationManager.class);
        mgr.createNotificationChannel(new NotificationChannel(
                CHANNEL_ID, "Потоковая озвучка", NotificationManager.IMPORTANCE_LOW));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // A newly created service MUST call startForeground quickly on Android 8+.
        startForeground(NOTIFICATION_ID, notification("Подключение к Termux…"));
        String action = intent == null ? ACTION_STOP : intent.getAction();
        if (ACTION_STOP.equals(action) || active) {
            stopPlayback();
            return START_NOT_STICKY;
        }
        String text = intent.getStringExtra(EXTRA_TEXT);
        if (text == null || text.isBlank()) {
            Toast.makeText(this, "Буфер обмена пуст", Toast.LENGTH_SHORT).show();
            stopSelf();
            return START_NOT_STICKY;
        }
        startPlayback(text);
        return START_NOT_STICKY;
    }

    private Notification notification(String message) {
        Intent stop = new Intent(this, StreamPlaybackService.class).setAction(ACTION_STOP);
        PendingIntent pendingStop = PendingIntent.getService(this, 0, stop,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle("Озвучить Stream — эксперимент")
                .setContentText(message)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(
                        android.R.drawable.ic_media_pause, "Остановить", pendingStop).build())
                .build();
    }

    private void updateNotification(String text) {
        getSystemService(NotificationManager.class).notify(NOTIFICATION_ID, notification(text));
    }

    private String newToken() {
        byte[] value = new byte[16];
        random.nextBytes(value);
        char[] hex = new char[value.length * 2];
        for (int i = 0; i < value.length; i++) {
            hex[2 * i] = HEX[(value[i] >> 4) & 15];
            hex[2 * i + 1] = HEX[value[i] & 15];
        }
        return new String(hex);
    }

    private void startPlayback(String text) {
        active = true;
        final int currentGeneration = ++generation;
        port = 28000 + random.nextInt(26000);
        token = newToken();
        final int chosenPort = port;
        final String chosenToken = token;
        Log.i(TAG, "Start stream session, localhost:" + chosenPort);
        try {
            Intent cmd = new Intent("com.termux.RUN_COMMAND");
            cmd.setClassName("com.termux", "com.termux.app.RunCommandService");
            cmd.putExtra("com.termux.RUN_COMMAND_PATH", SCRIPT);
            cmd.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{
                    "--port", Integer.toString(chosenPort), "--token", chosenToken});
            cmd.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
            cmd.putExtra("com.termux.RUN_COMMAND_STDIN", text);
            cmd.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            startService(cmd);
        } catch (Exception e) {
            fail(currentGeneration, "Termux не запустился: " + e.getClass().getSimpleName());
            return;
        }
        // Termux starts asynchronously. Poll readiness without blocking Android UI.
        new Thread(() -> awaitServer(currentGeneration, chosenPort, chosenToken),
                "tts-stream-connect").start();
    }

    private static String url(int port, String action, String token) {
        return "http://127.0.0.1:" + port + "/" + action + "/" + token;
    }

    private static boolean request(int port, String action, String token, int timeoutMs) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url(port, action, token)).openConnection();
            c.setRequestMethod("GET");
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setUseCaches(false);
            return c.getResponseCode() == HttpURLConnection.HTTP_NO_CONTENT;
        } catch (IOException ignored) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void awaitServer(int g, int p, String t) {
        long until = android.os.SystemClock.elapsedRealtime() + 12000;
        while (android.os.SystemClock.elapsedRealtime() < until) {
            if (g != generation) return;
            if (request(p, "health", t, 400)) {
                ui.post(() -> initializePlayer(g, p, t));
                return;
            }
            try {
                Thread.sleep(150);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
        ui.post(() -> fail(g, "Сервер Termux не запустился за 12 секунд"));
    }

    private void initializePlayer(int g, int p, String t) {
        if (!active || g != generation) return;
        updateNotification("Ожидание первого MP3-пакета…");
        MediaPlayer candidate = new MediaPlayer();
        player = candidate;
        try {
            candidate.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
            candidate.setOnPreparedListener(mp -> {
                if (g != generation || !active) return;
                Log.i(TAG, "MediaPlayer prepared; audio starting");
                mp.start();
                updateNotification("Воспроизведение · нажмите значок для остановки");
            });
            candidate.setOnCompletionListener(mp -> {
                Log.i(TAG, "Stream completed");
                if (g == generation) stopPlayback();
            });
            candidate.setOnErrorListener((mp, what, extra) -> {
                Log.e(TAG, "MediaPlayer error " + what + ":" + extra);
                fail(g, "Системный плеер отклонил поток MP3 (" + what + ")");
                return true;
            });
            candidate.setDataSource(url(p, "stream", t));
            candidate.prepareAsync();
        } catch (Exception e) {
            fail(g, "Ошибка потокового плеера: " + e.getClass().getSimpleName());
        }
    }

    private void fail(int g, String message) {
        if (!active || g != generation) return;
        Log.e(TAG, message);
        Toast.makeText(getApplicationContext(), message, Toast.LENGTH_LONG).show();
        stopPlayback();
    }

    private void stopPlayback() {
        if (!active) {
            stopSelf();
            return;
        }
        final int p = port;
        final String t = token;
        active = false;
        generation++;
        if (player != null) {
            MediaPlayer old = player;
            player = null;
            try { old.reset(); } catch (RuntimeException ignored) { }
            old.release();
        }
        // Cancellation also works when stopped while Termux is still booting.
        new Thread(() -> {
            long until = android.os.SystemClock.elapsedRealtime() + 11000;
            while (android.os.SystemClock.elapsedRealtime() < until) {
                if (request(p, "stop", t, 500)) return;
                try { Thread.sleep(200); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
            }
        }, "tts-stream-stop").start();
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public void onDestroy() {
        if (active) stopPlayback();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
