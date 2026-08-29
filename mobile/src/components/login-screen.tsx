import { useState } from 'react';
import { View, Text, Image, TextInput, Pressable, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, useColorScheme } from 'react-native';
import { router } from 'expo-router';
import { Colors, Brand, Fonts, Spacing, Radius, BiapLogo } from '@/constants/theme';
import { API_BASE } from '@/lib/api';
import { setDemoMode } from '@/lib/demo-mode';
import { storeAuthPayload } from '@/lib/auth-session';

type Props = { onLogin: () => void };
const DEMO_EMAIL = 'demo@biap.app';

export default function LoginScreen({ onLogin }: Props) {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleLogin = async () => {
    setErrorMsg('');
    if (!email || !password) {
      setErrorMsg('لطفاً ایمیل و رمز عبور را وارد کنید');
      return;
    }
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail, password }),
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

  return (
    <KeyboardAvoidingView style={[styles.container, { backgroundColor: colors.background }]} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Image source={BiapLogo} style={styles.logo} resizeMode="contain" />
      <Text style={[styles.title, { color: colors.text }]}>سرمایه‌گذاری هوشمند با BIAP</Text>
      <Text style={[styles.subtitle, { color: colors.textSecondary }]}>بورس ایران، ساده، سریع و همراه با تحلیل هوش مصنوعی</Text>
      <View style={{ height: 32 }} />
      <TextInput placeholder="ایمیل" placeholderTextColor={colors.textSecondary} value={email} onChangeText={setEmail} style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} keyboardType="email-address" autoCapitalize="none" textAlign="right" />
      <TextInput placeholder="رمز عبور" placeholderTextColor={colors.textSecondary} value={password} onChangeText={setPassword} secureTextEntry style={[styles.input, { color: colors.text, backgroundColor: colors.backgroundElement, borderColor: colors.backgroundSelected }]} textAlign="right" />
      {errorMsg ? <Text style={styles.error}>{errorMsg}</Text> : null}
      <Pressable style={[styles.button, { backgroundColor: Brand.primary, opacity: loading ? 0.7 : 1 }]} onPress={handleLogin} disabled={loading}>
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>ورود</Text>}
      </Pressable>
      <Pressable onPress={() => router.push('/register')} style={[styles.buttonOutline, { borderColor: colors.backgroundSelected }]}>
        <Text style={[styles.buttonOutlineText, { color: colors.text }]}>ثبت‌نام</Text>
      </Pressable>
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
  error: { color: '#E15B5B', fontSize: 13, marginBottom: 8, textAlign: 'center', fontFamily: Fonts.sans },
});
