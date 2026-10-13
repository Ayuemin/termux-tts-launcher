package io.github.ayuemin.ttsstream;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Toast;

import java.nio.charset.StandardCharsets;

/** Foreground-only clipboard read. The separate service owns all playback state. */
public final class StreamLaunchActivity extends Activity {
    private static final String PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final int REQUEST_CODE = 18;
    private static final int MAX_INPUT_BYTES = 96 * 1024;
    private boolean launched;
    private boolean waitingForPermission;

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && !launched && !waitingForPermission) {
            new Handler(Looper.getMainLooper()).post(this::openPlayback);
        }
    }

    private void openPlayback() {
        if (launched || waitingForPermission || isFinishing() || !hasWindowFocus()) return;
        if (checkSelfPermission(PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            waitingForPermission = true;
            requestPermissions(new String[]{PERMISSION}, REQUEST_CODE);
            return;
        }
        launched = true;
        try {
            String text = "";
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (clipboard != null && clipboard.hasPrimaryClip()) {
                ClipData clip = clipboard.getPrimaryClip();
                if (clip != null && clip.getItemCount() > 0) {
                    CharSequence contents = clip.getItemAt(0).coerceToText(this);
                    if (contents != null) text = contents.toString().trim();
                }
            }
            if (text.getBytes(StandardCharsets.UTF_8).length > MAX_INPUT_BYTES) {
                text = "";
                Toast.makeText(this, "Слишком большой текст (96 КБ)", Toast.LENGTH_SHORT).show();
            }
            Intent intent = new Intent(this, StreamPlaybackService.class);
            intent.setAction(StreamPlaybackService.ACTION_TOGGLE);
            intent.putExtra(StreamPlaybackService.EXTRA_TEXT, text);
            startForegroundService(intent);
        } catch (Exception e) {
            Toast.makeText(this, "Ошибка запуска: " + e.getClass().getSimpleName(), Toast.LENGTH_LONG).show();
        } finally {
            finish();
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] grants) {
        super.onRequestPermissionsResult(code, perms, grants);
        if (code != REQUEST_CODE) return;
        waitingForPermission = false;
        if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            if (hasWindowFocus()) new Handler(Looper.getMainLooper()).post(this::openPlayback);
        } else {
            new AlertDialog.Builder(this).setTitle("Нет доступа к Termux")
                    .setMessage("Разрешите «Run commands in Termux environment» для «Озвучить Stream» в настройках Android.")
                    .setPositiveButton("Понятно", (d, w) -> finish())
                    .setOnCancelListener(d -> finish()).show();
        }
    }
}
