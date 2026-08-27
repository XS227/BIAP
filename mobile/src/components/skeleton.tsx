import { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View, ViewStyle } from 'react-native';
import { useColorScheme } from 'react-native';
import { Colors } from '@/constants/theme';

export function SkeletonBox({ style }: { style?: ViewStyle }) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.8, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [opacity]);

  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];

  return (
    <Animated.View
      style={[
        skeletonStyles.box,
        { backgroundColor: colors.backgroundElement, opacity },
        style,
      ]}
    />
  );
}

const skeletonStyles = StyleSheet.create({
  box: { borderRadius: 8 },
});

export function StockRowSkeleton() {
  return (
    <View style={rowStyles.row}>
      <View style={rowStyles.left}>
        <SkeletonBox style={rowStyles.dot} />
        <SkeletonBox style={rowStyles.name} />
      </View>
      <View style={rowStyles.right}>
        <SkeletonBox style={rowStyles.price} />
        <SkeletonBox style={rowStyles.badge} />
      </View>
    </View>
  );
}

const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, paddingHorizontal: 16, paddingVertical: 16 },
  left: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  right: { alignItems: 'flex-end', gap: 6 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  name: { width: 80, height: 18 },
  price: { width: 80, height: 16 },
  badge: { width: 52, height: 14, borderRadius: 4 },
});
