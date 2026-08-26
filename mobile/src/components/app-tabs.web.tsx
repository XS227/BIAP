import {
  Tabs,
  TabList,
  TabTrigger,
  TabSlot,
  TabTriggerSlotProps,
  TabListProps,
} from 'expo-router/ui';
import { Image, Pressable, useColorScheme, View, StyleSheet, Text } from 'react-native';

import { Colors, Brand, Fonts, MaxContentWidth, Spacing, BiapLogo } from '@/constants/theme';

export default function AppTabs() {
  return (
    <Tabs>
      <TabSlot style={{ height: '100%' }} />
      <TabList asChild>
        <CustomTabList>
          <TabTrigger name="home" href="/" asChild>
            <TabButton accent={Brand.primary}>خانه</TabButton>
          </TabTrigger>
          <TabTrigger name="market" href="/market" asChild>
            <TabButton accent={Brand.positive}>بازار</TabButton>
          </TabTrigger>
          <TabTrigger name="orders" href="/orders" asChild>
            <TabButton accent={Brand.warning}>سفارش‌ها</TabButton>
          </TabTrigger>
          <TabTrigger name="portfolio" href="/portfolio" asChild>
            <TabButton accent={Brand.secondary}>پرتفوی</TabButton>
          </TabTrigger>
          <TabTrigger name="kiasha" href="/kiasha" asChild>
            <TabButton accent={Brand.primary}>کیاشا</TabButton>
          </TabTrigger>
          <TabTrigger name="more" href="/more" asChild>
            <TabButton>بیشتر</TabButton>
          </TabTrigger>
        </CustomTabList>
      </TabList>
    </Tabs>
  );
}

type TabButtonProps = TabTriggerSlotProps & { accent?: string; children?: React.ReactNode };

export function TabButton({ children, isFocused, accent, ...props }: TabButtonProps) {
    const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme ?? 'dark'];

  return (
    <Pressable {...props} style={({ pressed }) => [pressed && styles.pressed]}>
      <View
        style={[
          styles.tabButtonView,
          {
            backgroundColor: isFocused ? colors.backgroundSelected : 'transparent',
            borderBottomWidth: 2,
            borderBottomColor: isFocused ? (accent ?? Brand.primary) : 'transparent',
          },
        ]}
      >
        <Text
          style={[
            styles.tabLabel,
            { color: isFocused ? (accent ?? colors.text) : colors.textSecondary },
          ]}
        >
          {children}
        </Text>
      </View>
    </Pressable>
  );
}

export function CustomTabList(props: TabListProps) {
    const scheme = useColorScheme() ?? 'light';
  const colors = Colors[scheme ?? 'dark'];

  return (
    <View style={[styles.tabListContainer, { backgroundColor: colors.background, borderTopColor: colors.backgroundElement }]}>
      <View style={[styles.innerContainer, { maxWidth: MaxContentWidth }]}>
        <Image source={BiapLogo} style={styles.brandLogo} resizeMode="contain" />
        <View style={styles.tabs}>{props.children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  tabListContainer: {
    position: 'absolute',
    bottom: 0,
    width: '100%',
    borderTopWidth: 1,
    alignItems: 'center',
  },
  innerContainer: {
    width: '100%',
    flexDirection: 'row-reverse',
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.one,
    gap: Spacing.two,
  },
  brandLogo: {
    width: 64,
    height: 22,
    marginLeft: 'auto',
  },
  tabs: {
    flexDirection: 'row-reverse',
    gap: Spacing.one,
  },
  pressed: { opacity: 0.7 },
  tabButtonView: {
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
  },
  tabLabel: {
    fontFamily: Fonts.sans,
    fontSize: 14,
  },
});
