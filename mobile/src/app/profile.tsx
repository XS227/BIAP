import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, View, useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import { Colors, Brand, Fonts, Spacing, BottomTabInset, MaxContentWidth, Radius, ThemeColors } from '@/constants/theme';
import { useLogout } from '@/lib/logout-context';
import { authFetch, logoutAndClearAuthSession, storeAuthPayload } from '@/lib/auth-session';
import { API_BASE } from '@/lib/api';
import { getClientContext } from '@/lib/activity';

type UserData = { name?: string; fullName?: string; email?: string; id?: string | number; userId?: string | number };

function Avatar({ name }: { name: string; colors: ThemeColors }) {
  const words = name.trim().split(/\s+/);
  const initials = words.length > 1 ? (words[0][0] ?? '') + (words[1][0] ?? '') : (name[0] ?? '');
  return <View style={[avatarStyles.circle, { backgroundColor: Brand.primary }]}><Text style={avatarStyles.text}>{initials || '؟'}</Text></View>;
}
const avatarStyles = StyleSheet.create({ circle: { width: 80, height: 80, borderRadius: 40, alignItems: 'center', justifyContent: 'center' }, text: { color: '#fff', fontSize: 28, fontWeight: '700' } });

function InfoCard({ label, value, colors }: { label: string; value: string; colors: ThemeColors }) {
  return <View style={[infoStyles.row, { borderBottomColor: colors.backgroundSelected }]}><Text style={[infoStyles.val, { color: colors.text }]}>{value}</Text><Text style={[infoStyles.lbl, { color: colors.textSecondary }]}>{label}</Text></View>;
}
const infoStyles = StyleSheet.create({ row: { flexDirection: 'row-reverse', justifyContent: 'space-between', paddingVertical: Spacing.three, borderBottomWidth: StyleSheet.hairlineWidth }, lbl: { fontFamily: Fonts.sans, fontSize: 14 }, val: { fontFamily: Fonts.sans, fontSize: 14 } });

export default function ProfileScreen() {
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const logout = useLogout();
  const [user, setUser] = useState<UserData | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changing, setChanging] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');

  useEffect(() => {
    AsyncStorage.getItem('user').then((raw) => {
      if (raw) {
        try { setUser(JSON.parse(raw)); } catch { setUser(null); }
      }
    });
  }, []);

  const handleLogout = () => {
    Alert.alert('خروج از حساب', 'آیا مطمئن هستید که می‌خواهید خارج شوید؟', [
      { text: 'انصراف', style: 'cancel' },
      {
        text: 'خروج',
        style: 'destructive',
        onPress: async () => {
          await logoutAndClearAuthSession();
          logout();
        },
      },
    ]);
  };

  const changePassword = async () => {
    setPasswordError('');
    setPasswordMessage('');
    if (!currentPassword) { setPasswordError('رمز فعلی را وارد کنید'); return; }
    if (newPassword.length < 8) { setPasswordError('رمز جدید باید حداقل ۸ کاراکتر باشد'); return; }
    if (newPassword !== confirmPassword) { setPasswordError('رمز جدید و تکرار آن یکسان نیستند'); return; }

    setChanging(true);
    try {
      const context = await getClientContext();
      const res = await authFetch(`${API_BASE}/auth/change-password`, {
        method: 'POST',
        body: JSON.stringify({ currentPassword, newPassword, ...context }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setPasswordError(data?.error || 'تغییر رمز عبور انجام نشد');
        return;
      }
      if (data?.accessToken) await storeAuthPayload(data);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordMessage('رمز عبور با موفقیت تغییر کرد و نشست‌های قدیمی بسته شدند.');
    } catch {
      setPasswordError('اتصال به سرور برقرار نشد');
    } finally {
      setChanging(false);
    }
  };

  const displayName = user?.fullName ?? user?.name ?? user?.email?.split('@')[0] ?? 'کاربر';
  const id = user?.userId ?? user?.id;
  const appVersion = Constants.expoConfig?.version ?? Constants.nativeAppVersion ?? '—';

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
    <ScrollView contentContainerStyle={[styles.content, { paddingBottom: BottomTabInset + Spacing.four }]} keyboardShouldPersistTaps="handled">
      <View style={{ maxWidth: MaxContentWidth, width: '100%', alignSelf: 'center' }}>
        <View style={styles.header}><Text style={[styles.headerTitle, { color: colors.text }]}>حساب کاربری</Text></View>
        <View style={[styles.avatarSection, { backgroundColor: colors.backgroundElement }]}>
          <Avatar name={displayName} colors={colors} />
          <Text style={[styles.displayName, { color: colors.text }]}>{displayName}</Text>
          {user?.email ? <Text style={[styles.email, { color: colors.textSecondary }]}>{user.email}</Text> : null}
        </View>

        {user ? <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>اطلاعات کاربری</Text>
          <InfoCard label="نام" value={displayName} colors={colors} />
          {user.email ? <InfoCard label="ایمیل" value={user.email} colors={colors} /> : null}
          {id ? <InfoCard label="شناسه" value={String(id)} colors={colors} /> : null}
        </View> : null}

        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>تغییر رمز عبور</Text>
          <Text style={[styles.cardHint, { color: colors.textSecondary }]}>پس از تغییر رمز، نشست‌های قبلی حساب بسته می‌شوند.</Text>
          <TextInput placeholder="رمز فعلی" placeholderTextColor={colors.textSecondary} secureTextEntry value={currentPassword} onChangeText={setCurrentPassword} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected, backgroundColor: colors.background }]} textAlign="right" />
          <TextInput placeholder="رمز جدید (حداقل ۸ کاراکتر)" placeholderTextColor={colors.textSecondary} secureTextEntry value={newPassword} onChangeText={setNewPassword} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected, backgroundColor: colors.background }]} textAlign="right" />
          <TextInput placeholder="تکرار رمز جدید" placeholderTextColor={colors.textSecondary} secureTextEntry value={confirmPassword} onChangeText={setConfirmPassword} style={[styles.input, { color: colors.text, borderColor: colors.backgroundSelected, backgroundColor: colors.background }]} textAlign="right" />
          {passwordError ? <Text style={styles.error}>{passwordError}</Text> : null}
          {passwordMessage ? <Text style={styles.success}>{passwordMessage}</Text> : null}
          <Pressable onPress={changePassword} disabled={changing} style={[styles.passwordButton, { backgroundColor: Brand.primary, opacity: changing ? 0.65 : 1 }]}>
            {changing ? <ActivityIndicator color="#fff" /> : <Text style={styles.passwordButtonText}>ذخیره رمز جدید</Text>}
          </Pressable>
        </View>

        <View style={[styles.card, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>درباره اپ</Text>
          <InfoCard label="نام" value="BIAP Mobile" colors={colors} />
          <InfoCard label="نسخه" value={appVersion} colors={colors} />
          <InfoCard label="API" value="biap.dadashi.no" colors={colors} />
        </View>

        <Pressable style={({ pressed }) => [styles.logoutBtn, { backgroundColor: '#3d1a1a', opacity: pressed ? 0.75 : 1 }]} onPress={handleLogout}>
          <Text style={styles.logoutText}>خروج از حساب</Text>
        </Pressable>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  content: { paddingHorizontal: Spacing.three },
  header: { paddingTop: Spacing.four, paddingBottom: Spacing.three },
  headerTitle: { fontSize: 22, fontFamily: Fonts.sans, textAlign: 'right' },
  avatarSection: { alignItems: 'center', gap: Spacing.two, borderRadius: Spacing.three, paddingVertical: Spacing.four, marginBottom: Spacing.three },
  displayName: { fontSize: 20, fontFamily: Fonts.sans },
  email: { fontSize: 13, fontFamily: Fonts.mono },
  card: { borderRadius: Spacing.two, padding: Spacing.three, marginBottom: Spacing.three },
  cardTitle: { fontFamily: Fonts.sans, fontSize: 15, textAlign: 'right', marginBottom: Spacing.two, fontWeight: '700' },
  cardHint: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 19, textAlign: 'right', marginBottom: Spacing.two },
  input: { borderWidth: 1, borderRadius: Radius.md, paddingHorizontal: Spacing.three, paddingVertical: 12, marginBottom: Spacing.two, fontSize: 14, fontFamily: Fonts.sans },
  passwordButton: { borderRadius: Radius.md, paddingVertical: 13, alignItems: 'center', marginTop: Spacing.one },
  passwordButtonText: { color: '#fff', fontFamily: Fonts.sans, fontWeight: '700', fontSize: 14 },
  error: { color: Brand.negative, fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', marginBottom: 6 },
  success: { color: Brand.positive, fontFamily: Fonts.sans, fontSize: 12, textAlign: 'right', marginBottom: 6 },
  logoutBtn: { borderRadius: Spacing.two, paddingVertical: Spacing.three, alignItems: 'center', marginTop: Spacing.two },
  logoutText: { color: Brand.negative, fontFamily: Fonts.sans, fontSize: 16, fontWeight: '700' },
});
