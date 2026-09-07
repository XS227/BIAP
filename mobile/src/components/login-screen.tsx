import { useState } from 'react';
import { View, Text, Image, TextInput, Pressable, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, useColorScheme } from 'react-native';
import { Colors, Brand, Fonts, Spacing, Radius, BiapLogo } from '@/constants/theme';
import { API_BASE } from '@/lib/api';
import { setDemoMode } from '@/lib/demo-mode';
import { storeAuthPayload } from '@/lib/auth-session';
import { getClientContext } from '@/lib/activity';

type Props = { onLogin: () => void; onRegister: () => void };
type Mode = 'login' | 'forgot' | 'reset';
const DEMO_EMAIL = 'demo@biap.app';

export default function LoginScreen({ onLogin, onRegister }: Props) {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const handleLogin = async () => {
    setErrorMsg(''); setInfoMsg('');
    if (!email || !password) {
      setErrorMsg('لطفاً ایمیل و رمز عبور را وارد کنید');
      return;
    }
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const context = await getClientContext();
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail, password, ...context }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = typeof data?.detail?.error === 'string' ? data.detail.error : null;
        setErrorMsg(data?.error || detail || 'خطا در ورود');
        return;
      }
      await storeAuthPayload(data);
      await setDemoMode(normalizedEmail === DEMO_EMAIL);
      onLogin();
    } catch {
      setErrorMsg('اتصال به سرور برقرار نشد');
    } finally {
      setLoading(false);
    }
  };

  const requestReset = async () => {
    setErrorMsg(''); setInfoMsg('');
    if (!email.trim()) { setErrorMsg('ایمیل را وارد کنید'); return; }
    setLoading(true);
    try {
      const context = await getClientContext();
      const res = await fetch(`${API_BASE}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim().toLowerCase(), ...context }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setErrorMsg(data?.error || 'درخواست بازیابی انجام نشد'); return; }
      setInfoMsg(data?.message || 'اگر ایمیل ثبت شده باشد، کد بازیابی ارسال می‌شود.');
      setMode('reset');
    } catch {
      setErrorMsg('اتصال به سرور برقرار نشد');
    } finally { setLoading(false); }
  };

  const submitReset = async () => {
    setErrorMsg(''); setInfoMsg('');
    if (!resetCode.trim()) { setErrorMsg('کد بازیابی را وارد کنید'); return; }
    if (newPassword.length < 8) { setErrorMsg('رمز جدید باید حداقل ۸ کاراکتر باشد'); return; }
    if (newPassword !== confirmPassword) { setErrorMsg('رمز جدید و تکرار آن یکسان نیستند'); return; }
    setLoading(true);
    try {
      const context = await getClientContext();
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: resetCode.trim(), newPassword, ...context }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setErrorMsg(data?.error || 'کد بازیابی نامعتبر است'); return; }
      setPassword(''); setResetCode(''); setNewPassword(''); setConfirmPassword('');
      setMode('login');
      setInfoMsg(data?.message || 'رمز عبور تغییر کرد. اکنون وارد شوید.');
    } catch {
      setErrorMsg('اتصال به سرور برقرار نشد');
    } finally { setLoading(false); }
  };

  const title = mode === 'login' ? 'سرمایه‌گذاری هوشمند با BIAP' : mode === 'forgot' ? 'بازیابی رمز عبور' : 'ثبت رمز عبور جدید';
  const subtitle = mode === 'login' ? 'بورس ایران، ساده، سریع و همراه با تحلیل هوش مصنوعی' : mode === 'forgot' ? 'ایمیل حساب را وارد کنید تا کد یک‌بارمصرف ارسال شود' : 'کد ایمیل‌شده و رمز جدید را وارد کنید';

  return (
    <KeyboardAvoidingView style={[styles.container, { backgroundColor: colors.background }]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Image source={BiapLogo} style={styles.logo} resizeMode="contain" />
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{subtitle}</Text>
      <View style={{ height: 32 }} />

      {mode !== 'reset' ? <TextInput placeholder="ایمیل" placeholderTextColor={colors.textSecondary} value={email} onChangeText={setEmail} style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} keyboardType="email-address" autoCapitalize="none" textAlign="right" /> : null}
      {mode === 'login' ? <TextInput placeholder="رمز عبور" placeholderTextColor={colors.textSecondary} value={password} onChangeText={setPassword} secureTextEntry style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} textAlign="right" /> : null}
      {mode === 'reset' ? <>
        <TextInput placeholder="کد بازیابی" placeholderTextColor={colors.textSecondary} value={resetCode} onChangeText={setResetCode} autoCapitalize="characters" style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} textAlign="right" />
        <TextInput placeholder="رمز جدید (حداقل ۸ کاراکتر)" placeholderTextColor={colors.textSecondary} value={newPassword} onChangeText={setNewPassword} secureTextEntry style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} textAlign="right" />
        <TextInput placeholder="تکرار رمز جدید" placeholderTextColor={colors.textSecondary} value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} textAlign="right" />
      </> : null}

      {errorMsg ? <Text style={styles.error}>{errorMsg}</Text> : null}
      {infoMsg ? <Text style={[styles.info, { color: Brand.positive }]}>{infoMsg}</Text> : null}

      <Pressable style={[styles.button, { backgroundColor: Brand.primary, opacity: loading ? 0.7 : 1 }]} onPress={mode === 'login' ? handleLogin : mode === 'forgot' ? requestReset : submitReset} disabled={loading}>
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{mode === 'login' ? 'ورود' : mode === 'forgot' ? 'ارسال کد بازیابی' : 'تغییر رمز عبور'}</Text>}
      </Pressable>

      {mode === 'login' ? <>
        <Pressable onPress={() => { setMode('forgot'); setErrorMsg(''); setInfoMsg(''); }} style={styles.linkButton}><Text style={[styles.linkText, { color: Brand.primary }]}>رمز عبور را فراموش کرده‌اید؟</Text></Pressable>
        <Pressable onPress={onRegister} style={[styles.buttonOutline, { borderColor: colors.backgroundSelected }]}><Text style={[styles.buttonOutlineText, { color: colors.text }]}>ثبت‌نام</Text></Pressable>
      </> : <Pressable onPress={() => { setMode('login'); setErrorMsg(''); }} style={styles.linkButton}><Text style={[styles.linkText, { color: colors.textSecondary }]}>بازگشت به ورود</Text></Pressable>}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: Spacing.four },
  logo: { width: 140, height: 46 },
  title: { fontSize: 19, fontFamily: Fonts.sans, fontWeight: '700', marginTop: Spacing.three, textAlign: 'center' },
  subtitle: { fontSize: 14, marginTop: 8, textAlign: 'center', fontFamily: Fonts.sans },
  input: { width: '100%', borderWidth: 1, borderRadius: Radius.md, paddingHorizontal: Spacing.three, paddingVertical: 14, marginBottom: 14, fontSize: 16, fontFamily: Fonts.sans },
  button: { width: '100%', borderRadius: Radius.md, paddingVertical: 16, alignItems: 'center', marginTop: 8 },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700', fontFamily: Fonts.sans },
  buttonOutline: { width: '100%', borderRadius: Radius.md, paddingVertical: 16, alignItems: 'center', marginTop: Spacing.two, borderWidth: 1 },
  buttonOutlineText: { fontSize: 16, fontWeight: '700', fontFamily: Fonts.sans },
  linkButton: { paddingVertical: 12 },
  linkText: { fontSize: 13, fontFamily: Fonts.sans },
  error: { color: '#E15B5B', fontSize: 13, marginBottom: 8, textAlign: 'center', fontFamily: Fonts.sans },
  info: { fontSize: 13, marginBottom: 8, textAlign: 'center', fontFamily: Fonts.sans, lineHeight: 20 },
});
