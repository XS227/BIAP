import { useCallback, useState } from 'react';
import { FlatList, Pressable, SafeAreaView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { BottomTabInset, Brand, Colors, Fonts, MaxContentWidth, Radius, Spacing } from '@/constants/theme';
import { listFavorites, FavoriteSymbol } from '@/lib/favorites';
import { SymbolLogo } from '@/components/symbol-logo';

export default function FavoritesScreen() {
  const colors = useColorScheme() === 'dark' ? Colors.dark : Colors.light;
  const [items, setItems] = useState<FavoriteSymbol[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setItems(await listFavorites());
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}> 
    <View style={[styles.wrap, { maxWidth: MaxContentWidth }]}> 
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={[styles.back, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.backText, { color: colors.text }]}>←</Text></Pressable>
        <View style={styles.headerCopy}><Text style={[styles.title, { color: colors.text }]}>علاقه‌مندی‌ها</Text><Text style={[styles.sub, { color: colors.textSecondary }]}>نمادهای ذخیره‌شده روی این دستگاه</Text></View>
      </View>
      <FlatList
        data={items}
        keyExtractor={(item) => item.code}
        contentContainerStyle={{ paddingBottom: BottomTabInset + Spacing.four }}
        ListEmptyComponent={!loading ? <View style={[styles.empty, { backgroundColor: colors.backgroundElement }]}><Text style={[styles.emptyTitle, { color: colors.text }]}>هنوز نمادی ذخیره نشده</Text><Text style={[styles.emptyBody, { color: colors.textSecondary }]}>در صفحه هر سهم روی ★ بزن تا اینجا اضافه شود.</Text><Pressable onPress={() => router.push('/market')} style={styles.marketBtn}><Text style={styles.marketBtnText}>رفتن به بازار</Text></Pressable></View> : null}
        renderItem={({ item }) => <Pressable onPress={() => router.push(`/stock/${encodeURIComponent(item.code)}`)} style={[styles.row, { backgroundColor: colors.backgroundElement }]}>
          <Text style={[styles.chevron, { color: colors.textSecondary }]}>‹</Text>
          <View style={styles.copy}><Text style={[styles.symbol, { color: colors.text }]}>{item.symbol}</Text><Text style={[styles.name, { color: colors.textSecondary }]} numberOfLines={1}>{item.name}</Text><Text style={[styles.market, { color: colors.textSecondary }]}>{item.market ?? 'BIAP Market'}</Text></View>
          <SymbolLogo symbol={item.symbol} size={42} />
        </Pressable>}
      />
    </View>
  </SafeAreaView>;
}

const styles = StyleSheet.create({
  safe:{flex:1},wrap:{width:'100%',alignSelf:'center',paddingHorizontal:Spacing.three},
  header:{flexDirection:'row-reverse',alignItems:'center',gap:Spacing.three,paddingTop:Spacing.three,paddingBottom:Spacing.three},
  back:{width:38,height:38,borderRadius:19,alignItems:'center',justifyContent:'center'},backText:{fontSize:19},headerCopy:{flex:1,alignItems:'flex-end'},
  title:{fontFamily:Fonts.sans,fontSize:22,fontWeight:'900'},sub:{fontFamily:Fonts.sans,fontSize:11,marginTop:3},
  row:{flexDirection:'row',alignItems:'center',gap:Spacing.three,borderRadius:Radius.md,padding:Spacing.three,marginBottom:Spacing.two},
  copy:{flex:1,alignItems:'flex-end'},symbol:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},name:{fontFamily:Fonts.sans,fontSize:11,marginTop:2},market:{fontFamily:Fonts.mono,fontSize:9,marginTop:3},chevron:{fontSize:20},
  empty:{borderRadius:Radius.lg,padding:Spacing.four,alignItems:'center',marginTop:Spacing.four},emptyTitle:{fontFamily:Fonts.sans,fontSize:16,fontWeight:'900'},emptyBody:{fontFamily:Fonts.sans,fontSize:12,lineHeight:20,textAlign:'center',marginTop:Spacing.two},marketBtn:{backgroundColor:Brand.primary,borderRadius:Radius.md,paddingHorizontal:18,paddingVertical:11,marginTop:Spacing.three},marketBtnText:{color:'#fff',fontFamily:Fonts.sans,fontSize:12,fontWeight:'900'}
});
