import org.jf.dexlib2.DexFileFactory;
import org.jf.dexlib2.Opcode;
import org.jf.dexlib2.Opcodes;
import org.jf.dexlib2.iface.ClassDef;
import org.jf.dexlib2.iface.Method;
import org.jf.dexlib2.iface.instruction.Instruction;
import org.jf.dexlib2.immutable.ImmutableClassDef;
import org.jf.dexlib2.immutable.ImmutableDexFile;
import org.jf.dexlib2.immutable.ImmutableMethod;
import org.jf.dexlib2.immutable.ImmutableMethodImplementation;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction11x;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction22c;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction35c;
import org.jf.dexlib2.immutable.instruction.ImmutableInstruction51l;
import org.jf.dexlib2.immutable.reference.ImmutableFieldReference;
import org.jf.dexlib2.immutable.reference.ImmutableMethodReference;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/**
 * classes7.dex 定点改动（单次读写，绝不要连续重写两次）。
 *
 * 只做一件事：把免广告到期时间的读取 lambda 改成恒返回"未过期"。
 *
 *   VideoDataStore$currentAdFreeExpiresAt$$inlined$map$1$2.emit(Object; Continuation)Object
 *     -> 无条件向下游 collector 发一个超大 Long
 *
 * 效果等价于 DataStore 里 ad_free_expires_at 永远没有过期，
 * 「看广告领特权」弹窗因此不再出现，而且这个改动写死在代码里，
 * 全新安装同样生效（DataStore 那份是运行时数据，随 APK 分发不了）。
 *
 * ⚠️ 不要顺手 patch Lx6;->d：那是通用的图片卡片 Composable，
 *    内容和广告共用，改成 return-void 会导致正常图片/播放链路一起失效。
 */
public class PatchClasses7v2 {

    private static final String AD_CLASS =
            "Lcyc/data/datastore/VideoDataStore$currentAdFreeExpiresAt$$inlined$map$1$2;";
    private static final long BIG = 4102444800000L;   // ~2100-01-01 (ms)

    public static void main(String[] args) throws Exception {
        String in = args[0], out = args[1];
        org.jf.dexlib2.iface.DexFile dex =
                DexFileFactory.loadDexFile(new File(in), Opcodes.forApi(34));

        List<ClassDef> outClasses = new ArrayList<ClassDef>();
        int p = 0;

        for (ClassDef cd : dex.getClasses()) {
            List<Method> direct = new ArrayList<Method>();
            for (Method m : cd.getDirectMethods()) direct.add(m);
            List<Method> virtual = new ArrayList<Method>();
            for (Method m : cd.getVirtualMethods()) virtual.add(m);
            boolean touched = false;

            if (cd.getType().equals(AD_CLASS)) {
                for (int pass = 0; pass < 2; pass++) {
                    List<Method> list = (pass == 0) ? direct : virtual;
                    for (int i = 0; i < list.size(); i++) {
                        Method m = list.get(i);
                        if (!m.getName().equals("emit")
                                || !m.getReturnType().equals("Ljava/lang/Object;")
                                || m.getImplementation() == null) {
                            continue;
                        }
                        List<Instruction> body = new ArrayList<Instruction>();
                        // v0 = collector, v1:v2 = long, p0=3 p1=4 p2=5
                        body.add(new ImmutableInstruction22c(Opcode.IGET_OBJECT, 0, 3,
                                new ImmutableFieldReference(AD_CLASS, "b", "Lkw2;")));
                        body.add(new ImmutableInstruction51l(Opcode.CONST_WIDE, 1, BIG));
                        body.add(new ImmutableInstruction35c(Opcode.INVOKE_STATIC, 2, 1, 2, 0, 0, 0,
                                new ImmutableMethodReference("Ljava/lang/Long;", "valueOf",
                                        Collections.singletonList("J"), "Ljava/lang/Long;")));
                        body.add(new ImmutableInstruction11x(Opcode.MOVE_RESULT_OBJECT, 1));
                        body.add(new ImmutableInstruction35c(Opcode.INVOKE_INTERFACE, 3, 0, 1, 5, 0, 0,
                                new ImmutableMethodReference("Lkw2;", "emit",
                                        Arrays.asList("Ljava/lang/Object;", "Lwj1;"),
                                        "Ljava/lang/Object;")));
                        body.add(new ImmutableInstruction11x(Opcode.MOVE_RESULT_OBJECT, 0));
                        body.add(new ImmutableInstruction11x(Opcode.RETURN_OBJECT, 0));

                        list.set(i, new ImmutableMethod(m.getDefiningClass(), m.getName(),
                                m.getParameters(), m.getReturnType(), m.getAccessFlags(),
                                m.getAnnotations(), m.getHiddenApiRestrictions(),
                                new ImmutableMethodImplementation(6, body, null, null)));
                        p++;
                        touched = true;
                        System.out.println("[patch] emit -> BIG=" + BIG + " (list=" + pass + ")");
                    }
                }
            }

            if (!touched) outClasses.add(cd);
            else outClasses.add(new ImmutableClassDef(
                    cd.getType(), cd.getAccessFlags(), cd.getSuperclass(), cd.getInterfaces(),
                    cd.getSourceFile(), cd.getAnnotations(), cd.getStaticFields(),
                    cd.getInstanceFields(), direct, virtual));
        }

        DexFileFactory.writeDexFile(out, new ImmutableDexFile(Opcodes.forApi(34), outClasses));
        System.out.println("[done] patched=" + p);
        if (p == 0) System.exit(1);
    }
}
