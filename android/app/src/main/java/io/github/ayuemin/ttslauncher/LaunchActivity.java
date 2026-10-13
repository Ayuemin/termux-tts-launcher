package io.github.ayuemin.ttslauncher;

import android.Manifest;
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

/** One foreground, translucent Activity: read clipboard only after gaining focus. */
public final class LaunchActivity extends Activity {
    private static final String RUN_PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String TERMUX_PACKAGE = "com.termux";
    private static final String RUN_SERVICE = "com.termux.app.RunCommandService";
    private static final String SCRIPT = "/data/data/com.termux/files/usr/bin/tts-launcher-play";
    // Keep far below the Android Binder transaction limit; never silently truncate.
    private static final int MAX_UTF8_BYTES = 96 * 1024;
    private static final int PERMISSION_REQUEST = 12;

    private boolean launched = false;
    private boolean permissionPending = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // No conventional UI: Android's clipboard access requires foreground focus.
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus && !launched && !permissionPending) {
            new Handler(Looper.getMainLooper()).post(this::launchFromClipboard);
        }
    }

    private void launchFromClipboard() {
        if (launched || permissionPending || isFinishing() || !hasWindowFocus()) return;
        if (checkSelfPermission(RUN_PERMISSION) != PackageManager.PERMISSION_GRANTED) {
            permissionPending = true;
            requestPermissions(new String[]{RUN_PERMISSION}, PERMISSION_REQUEST);
            return;
        }
        launched = true;
        try {
            ClipboardManager clipboard = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (clipboard == null || !clipboard.hasPrimaryClip()) {
                message("Буфер обмена пуст");
                return;
            }
            ClipData clip = clipboard.getPrimaryClip();
            if (clip == null || clip.getItemCount() == 0) {
                message("Не удалось получить текст из буфера");
                return;
            }
            CharSequence content = clip.getItemAt(0).coerceToText(this);
            String text = content == null ? "" : content.toString().trim();
            if (text.isEmpty()) {
                message("В буфере нет текста");
                return;
            }
            if (text.getBytes(StandardCharsets.UTF_8).length > MAX_UTF8_BYTES) {
                message("Текст слишком большой (максимум 96 КБ)");
                return;
            }
            Intent intent = new Intent("com.termux.RUN_COMMAND");
            intent.setClassName(TERMUX_PACKAGE, RUN_SERVICE);
            intent.putExtra("com.termux.RUN_COMMAND_PATH", SCRIPT);
            intent.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
            intent.putExtra("com.termux.RUN_COMMAND_STDIN", text);
            intent.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
            startService(intent);
            message("Готовлю озвучку…");
        } catch (SecurityException e) {
            error("Разрешите запуск команд Termux в настройках приложения");
        } catch (IllegalStateException e) {
            error("Termux не разрешает фоновый запуск. Проверьте настройки Termux");
        } catch (Exception e) {
            error("Не удалось запустить Termux: " + e.getClass().getSimpleName());
        } finally {
            // The background command continues after we return to the original app.
            finish();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(requestCode, permissions, grants);
        if (requestCode != PERMISSION_REQUEST) return;
        permissionPending = false;
        if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            // Clipboard read must happen only after the window regains foreground focus.
            if (hasWindowFocus()) new Handler(Looper.getMainLooper()).post(this::launchFromClipboard);
        } else {
            new AlertDialog.Builder(this)
                    .setTitle("Нужен доступ к Termux")
                    .setMessage("Разрешите «Run commands in Termux environment» в настройках Android → Приложения → Озвучить → Разрешения → Дополнительные разрешения.")
                    .setPositiveButton("Понятно", (d, w) -> finish())
                    .setOnCancelListener(d -> finish())
                    .show();
        }
    }

    private void message(String message) {
        Toast.makeText(getApplicationContext(), message, Toast.LENGTH_SHORT).show();
    }

    private void error(String message) { message(message); }
}
