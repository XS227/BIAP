from pathlib import Path

roots = list(Path('android/app/src/main/java').rglob('MainApplication.kt'))
if len(roots) != 1:
    raise SystemExit(f'Expected exactly one MainApplication.kt, found {len(roots)}')

path = roots[0]
text = path.read_text(encoding='utf-8')

import_marker = 'import android.app.Application\n'
imports = '''import android.app.Application
import com.facebook.react.modules.network.OkHttpClientFactory
import com.facebook.react.modules.network.OkHttpClientProvider
import okhttp3.ConnectionSpec
import okhttp3.Dns
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.TlsVersion
import java.net.InetAddress
'''
if 'OkHttpClientProvider' not in text:
    if import_marker not in text:
        raise SystemExit('Could not locate MainApplication import marker')
    text = text.replace(import_marker, imports, 1)

oncreate_marker = '    super.onCreate()\n'
compat_code = '''    // BIAP Global Android network compatibility:
    // - keeps normal TLS certificate/hostname verification
    // - prefers the known BIAP origin IP to survive poisoned/broken DNS
    // - uses TLS 1.2 + HTTP/1.1 for compatibility with restrictive mobile middleboxes
    OkHttpClientProvider.setOkHttpClientFactory(object : OkHttpClientFactory {
      override fun createNewNetworkModuleClient(): OkHttpClient {
        val tls12 = ConnectionSpec.Builder(ConnectionSpec.MODERN_TLS)
          .tlsVersions(TlsVersion.TLS_1_2)
          .build()
        return OkHttpClientProvider.createClientBuilder()
          .dns(object : Dns {
            override fun lookup(hostname: String): List<InetAddress> {
              if (hostname.equals("biap.dadashi.no", ignoreCase = true)) {
                val fixed = InetAddress.getByName("5.249.252.88")
                val system = runCatching { Dns.SYSTEM.lookup(hostname) }.getOrDefault(emptyList())
                return listOf(fixed) + system.filterNot { it.hostAddress == fixed.hostAddress }
              }
              return Dns.SYSTEM.lookup(hostname)
            }
          })
          .connectionSpecs(listOf(tls12))
          .protocols(listOf(Protocol.HTTP_1_1))
          .retryOnConnectionFailure(true)
          .build()
      }
    })
'''
if 'BIAP Global Android network compatibility' not in text:
    if oncreate_marker not in text:
        raise SystemExit('Could not locate onCreate super call')
    text = text.replace(oncreate_marker, oncreate_marker + compat_code, 1)

path.write_text(text, encoding='utf-8')
print(f'Patched {path}')
