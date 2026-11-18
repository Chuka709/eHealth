/**
 * The privacy policy, terms of use and account deletion pages (Phase 8.1; docs/04 §5,
 * docs/08 "Дэлгүүрт гаргах", BETA B4). DRAFTS for the lawyer (Q12): every statement here
 * describes what the app actually does - change the code and this together (reviewed against
 * the code by security-, medical- and ui-reviewer, 8.1). Bracketed placeholders are the
 * company's to fill in before release (content.test.ts refuses them with LEGAL_RELEASE=1).
 */

export type LegalLocale = "mn" | "en";
export type LegalPage = "privacy" | "terms" | "deletion";

/** A paragraph, or a list (an array of items). */
export type Block = string | readonly string[];

export interface LegalDoc {
  title: string;
  description: string;
  draft: string;
  updated: string;
  sections: readonly { heading: string; blocks: readonly Block[] }[];
}

const UPDATED = "2026.11.18";

const mnDraft =
  "НООРОГ — хуульчаар хянуулж, компанийн мэдээллээр бөглөсний дараа хүчин төгөлдөр болно. " +
  "Дөрвөлжин хаалттай хэсгийг компани бөглөнө.";
const enDraft =
  "DRAFT — in force only after legal review and once the company's details are filled in. " +
  "Bracketed parts are for the company to complete.";

const privacyMn: LegalDoc = {
  title: "Нууцлалын бодлого",
  description: "LabTrack MN апп таны мэдээллийг юунд, хэрхэн ашиглаж хамгаалдаг вэ.",
  draft: mnDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "1. Хэн хариуцах вэ",
      blocks: [
        "LabTrack MN нь эрхтэн шилжүүлэн суулгуулсан хүмүүст зориулсан хаалттай бүлгийн апп. Таны мэдээллийг хариуцагч нь [Компанийн нэр], [хаяг] (цаашид «компани»). Холбоо барих: [имэйл], [утас].",
        "Энэ бодлого Монгол Улсын Хүний хувийн мэдээлэл хамгаалах тухай хуульд (2021) нийцүүлэхээр бичигдсэн. Эрүүл мэндийн мэдээлэл нь эмзэг мэдээлэл тул зөвхөн таны тусгай зөвшөөрлөөр боловсруулна.",
      ],
    },
    {
      heading: "2. Ямар мэдээлэл цуглуулах вэ",
      blocks: [
        [
          "Бүртгэл: хэрэглэгчийн нэр, харагдах нэр, утасны дугаар (тусламж хүсэхэд таныг таних), нууц үг — буцааж тайлах боломжгүй хэлбэрээр хадгална (нууц үгийг өөрийг нь хэн ч, админ ч мэдэхгүй).",
          "Профайл: нэр, төрсөн огноо, хүйс; хүүхдийн профайлыг эцэг эх эсвэл асран хамгаалагч нь оруулна.",
          "Эрүүл мэндийн мэдээлэл (таны оруулснаар): шилжүүлэн суулгалт, эм ба тун, уусан/алгассан тэмдэглэл, эмчилгээ ба үйл явдал, амин үзүүлэлт, харшил, яаралтай үед холбоо барих хүмүүс, товлол, эмчээс асуух асуулт, шинжилгээний баримт (зураг, PDF) ба хариу.",
          "Төхөөрөмж: мэдэгдэл хүргэх төхөөрөмжийн дугаар, сануулга яг цагтаа ирэх зөвшөөрөл өгсөн эсэх, нэвтэрсэн төхөөрөмжүүд.",
          "Аюулгүй байдлын бүртгэл: хэн, хэзээ, ямар үйлдэл хийсэн — зөвхөн дугаар, утга агуулахгүй.",
          "Хэрэглээний тоо: нэр, эрүүл мэндийн утгагүй, таныг шууд илэрхийлэхгүй дугаартай тоо (жишээ нь дэлгэц нээгдсэн тоо).",
        ],
        "Бид байршил, утасны харилцагчид, зар сурталчилгааны дугаар цуглуулахгүй. Скан хийсэн зургийг утасны галерейд хадгалахгүй.",
      ],
    },
    {
      heading: "3. Ямар зорилгоор ашиглах вэ",
      blocks: [
        [
          "Таны мэдээллийг цэгцэлж хадгалах, хандлагыг харуулах, эмийн сануулга, яаралтай тусламжийн карт.",
          "Таны сонгосон хүмүүстэй (асран хамгаалагч, эмч, зөвхөн үзэх эрхтэй хүн) эсвэл линкээр хуваалцах.",
          "Аппыг аюулгүй, найдвартай ажиллуулах (нэвтрэлт, аюулгүй байдлын бүртгэл, алдаа засах).",
        ],
        "Апп онош тавихгүй, эмчилгээ, эмийн тун санал болгохгүй, эмийн харилцан үйлчлэл шалгахгүй. Таны мэдээллийг зар сурталчилгаанд ашиглахгүй, худалдахгүй.",
      ],
    },
    {
      heading: "4. Хиймэл оюун ухаанаар (AI) баримт унших — сонголттой",
      blocks: [
        "Шинжилгээний PDF-ийг AI-аар уншуулах нь тусдаа хоёр зөвшөөрөлтэй: «AI боловсруулалт» ба «гадаад серверт дамжуулах». Анхдагчаар унтраалттай; зөвшөөрөөгүй бол хариуг гараар оруулна.",
        "Зөвшөөрсөн үед нэр, регистр, утас гэх мэт таныг таних мэдээллийг хассан текстийг [Anthropic PBC, АНУ] руу илгээнэ. AI зөвхөн баримтаас утгыг уншина — тайлбар, зөвлөгөө өгөхгүй, чат байхгүй. Уншсан утга бүр таныг баталтал «ноорог» хэвээр, хандлага, нүүр хуудсанд орохгүй. Гагцхүү критик байж болзошгүй утга илэрвэл баталгаажаагүй ч танд болон «критик анхааруулга» асаасан асран хамгаалагчид утгагүй анхааруулга очно.",
        "Үйлчилгээ үзүүлэгчтэй өгөгдөл боловсруулах гэрээгээр мэдээллийг загвар сургахад ашиглахгүй, [хадгалах нөхцөл]-өөр хязгаарлана. Зөвшөөрлөө хүссэн үедээ Тохиргоо → Зөвшөөрлүүд-ээс татаж болно.",
      ],
    },
    {
      heading: "5. Хэнтэй хуваалцах вэ",
      blocks: [
        [
          "Зөвхөн таны урьсан хүмүүс: асран хамгаалагч (тунгийн мэдэгдэл авна), эмч (зорилт, тэмдэглэл бичнэ), зөвхөн үзэх эрхтэй хүн. Хэн хэзээ нээснийг та харж, эрхийг хүссэн үедээ цуцална.",
          "Линк ба QR: хугацаатай (30 хоногоос ихгүй), PIN кодтой, зөвхөн таны сонгосон хэсэг; та цуцалж болно.",
          "Админ (компанийн ажилтан) таны эрүүл мэндийн мэдээллийг харахгүй — систем хаалттай. Онцгой тохиолдолд хоёр админ батлах ба бүртгэгдэнэ.",
          "Хуулиар шаардсан үед эрх бүхий байгууллагад.",
        ],
        "Мэдээллийг [hosting үйлчилгээ үзүүлэгч, байршил — Монгол Улсад эсэх] дээр хадгална. Мэдэгдэл (push) илгээхэд Google/Apple-ийн үйлчилгээ ашиглана — мэдэгдэлд эмийн нэр, эрүүл мэндийн утга орохгүй. Утсан дээрх эмийн сануулгад анхдагчаар эмийн нэр харагдахгүй; та тохиргоонд өөрчилж болно.",
      ],
    },
    {
      heading: "6. Хамгаалалт",
      blocks: [
        [
          "Дамжуулалт шифрлэгдсэн (HTTPS). Баримтын файл бүр өөрийн түлхүүрээр шифрлэгдэж хадгалагдана.",
          "Хэн ямар мэдээлэл харж болохыг сервер бичлэг бүрээр шалгана.",
          "Утсан дээрх хуулбар шифрлэгдсэн; гарахад устна. Биометр/PIN түгжээ.",
          "Нууц үгийг буцааж тайлах боломжгүй хэлбэрээр хадгална; бүх төхөөрөмжөөс нэг дор гарах боломжтой.",
        ],
      ],
    },
    {
      heading: "7. Хадгалах хугацаа ба устгах",
      blocks: [
        "Таны мэдээлэл аккаунт идэвхтэй байх хугацаанд хадгалагдана. Аккаунтаа устгавал бүх төхөөрөмжөөс шууд гарч, 30 хоногийн дараа бүх мэдээлэл (эрүүл мэндийн мэдээлэл, баримтын файл) системээс бүрмөсөн устна. 30 хоногийн дотор зөвхөн таны хүсэлтээр, хүн таних шалгалтын дараа сэргээж болно.",
        "Нөөц хуулбарт үлдсэн мэдээлэл [N] хоногийн дотор дарагдаж устна. Аюулгүй байдлын бүртгэл (утгагүй, зөвхөн дугаар) [хугацаа] хадгалагдана.",
        "Устгах заавар: доорх «Аккаунт устгах» холбоос.",
      ],
    },
    {
      heading: "8. Таны эрх",
      blocks: [
        [
          "Мэдээллээ харах, засах — апп дотор.",
          "Экспорт — «Эмчид үзүүлэх» PDF, JSON, FHIR (эмнэлгийн программд зориулсан файл).",
          "Устгах — апп дотор, эсвэл «Аккаунт устгах» хуудасны дагуу.",
          "Зөвшөөрлөө татах — Тохиргоо → Зөвшөөрлүүд (заавал зөвшөөрлийг татвал апп ашиглах боломжгүй болно).",
          "Гомдол гаргах — компанид [имэйл], эсвэл эрх бүхий байгууллагад.",
        ],
      ],
    },
    {
      heading: "9. Хүүхэд",
      blocks: [
        "18 хүртэлх насны хүүхдийн профайлыг эцэг эх эсвэл хууль ёсны асран хамгаалагч нь үүсгэж, зөвшөөрлийг өгнө. Хүүхэд 18 нас хүрэхэд профайлыг өөрийнх нь аккаунт руу шилжүүлэх талаар [компанитай холбогдоно / журам].",
      ],
    },
    {
      heading: "10. Зөрчил гарвал",
      blocks: [
        "Мэдээллийн аюулгүй байдлын зөрчил илэрвэл компани хуульд заасан хугацаанд эрх бүхий байгууллага болон өртсөн хэрэглэгчдэд мэдэгдэнэ.",
      ],
    },
    {
      heading: "11. Өөрчлөлт",
      blocks: [
        "Энэ бодлого өөрчлөгдвөл апп дотор мэдэгдэж, шаардлагатай бол зөвшөөрлийг дахин асууна.",
      ],
    },
  ],
};

const privacyEn: LegalDoc = {
  title: "Privacy policy",
  description: "What LabTrack MN uses your data for, and how it is protected.",
  draft: enDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "1. Who is responsible",
      blocks: [
        "LabTrack MN is a closed-group app for organ transplant recipients. Your data's controller is [Company name], [address] (the “company”). Contact: [email], [phone].",
        "This policy is written to comply with Mongolia's Law on the Protection of Personal Information (2021). Health data is sensitive data and is processed only with your specific consent.",
      ],
    },
    {
      heading: "2. What we collect",
      blocks: [
        [
          "Account: username, display name, phone number (to identify you when you ask for help), and your password — stored in a form that cannot be turned back (nobody, not even an administrator, knows the password itself).",
          "Profile: name, date of birth, sex; a child's profile is entered by a parent or guardian.",
          "Health data (as you enter it): transplants, medicines and doses, doses taken or skipped, treatments and events, vital signs, allergies, emergency contacts, appointments, questions for the doctor, lab documents (images, PDF) and results.",
          "Device: the identifier used to deliver notifications, whether on-time reminders are allowed, signed-in devices.",
          "Security log: who did what and when — identifiers only, never values.",
          "Usage counts: without names or health values, under an identifier that does not name you (e.g. how often a screen is opened).",
        ],
        "We do not collect location, contacts or advertising IDs. Scanned images are never saved to the phone's gallery.",
      ],
    },
    {
      heading: "3. Why we use it",
      blocks: [
        [
          "To organise and keep your data, show trends, remind you of medicines, and provide the emergency card.",
          "To share with people you choose (caregivers, doctors, view-only people) or by link.",
          "To run the app safely and reliably (sign-in, security log, fixing errors).",
        ],
        "The app does not diagnose, does not suggest treatment or medicine doses and does not check drug interactions. Your data is never used for advertising or sold.",
      ],
    },
    {
      heading: "4. Reading documents with AI — optional",
      blocks: [
        "Having a lab PDF read by AI needs two separate consents: “AI processing” and “transfer to a server abroad”. Both are off by default; without them you enter results by hand.",
        "With them, only text with your identifying details (name, ID number, phone, etc.) removed is sent to [Anthropic PBC, USA]. The AI only reads values from the document — no explanations, no advice, no chat. Every value it reads stays a “draft” until you confirm it and never reaches your trends or home screen before that. Only when a possibly critical value is found does an alert without the value go to you and to caregivers who turned on critical alerts, before you confirm.",
        "A data processing agreement prevents its use for model training and limits retention to [terms]. You can withdraw these consents at any time in Settings → Consents.",
      ],
    },
    {
      heading: "5. Who we share with",
      blocks: [
        [
          "Only people you invite: caregivers (dose alerts), doctors (targets and notes), view-only people. You see who opened your profile and when, and can revoke access at any time.",
          "Links and QR codes: time-limited (no more than 30 days), PIN-protected, only the sections you choose; you can revoke them.",
          "Administrators (company staff) cannot see your health data — the system blocks it. Exceptional access needs two administrators and is logged.",
          "Authorities, when the law requires it.",
        ],
        "Data is hosted by [hosting provider, location — whether in Mongolia]. Notifications (push) use Google/Apple services — they never contain medicine names or health values. Medicine reminders on the phone show no medicine name by default; you can change this in settings.",
      ],
    },
    {
      heading: "6. Protection",
      blocks: [
        [
          "Encrypted in transit (HTTPS). Every document file is stored encrypted with its own key.",
          "The server checks, record by record, who may see what.",
          "The copy on your phone is encrypted and erased when you sign out. Biometric/PIN lock.",
          "Passwords are stored in a form that cannot be turned back; you can sign out of every device at once.",
        ],
      ],
    },
    {
      heading: "7. Retention and deletion",
      blocks: [
        "Your data is kept while your account is active. When you delete your account you are signed out of every device at once, and 30 days later all data (health data, document files) is erased from the system permanently. Within those 30 days it can be restored only at your request, after an identity check.",
        "Data left in backups is overwritten within [N] days. The security log (identifiers only, no values) is kept for [period].",
        "How to delete: the “Delete account” link below.",
      ],
    },
    {
      heading: "8. Your rights",
      blocks: [
        [
          "See and correct your data — in the app.",
          "Export — the “summary for the doctor” PDF, JSON and FHIR (a file for medical software).",
          "Delete — in the app, or as described on the “Delete account” page.",
          "Withdraw consent — Settings → Consents (withdrawing a required consent means the app can no longer be used).",
          "Complain — to the company at [email], or to the competent authority.",
        ],
      ],
    },
    {
      heading: "9. Children",
      blocks: [
        "A profile of a child under 18 is created, and its consents given, by a parent or legal guardian. When the child turns 18, moving the profile to their own account is arranged [with the company / procedure].",
      ],
    },
    {
      heading: "10. If a breach happens",
      blocks: [
        "If a data security breach is found, the company notifies the competent authority and the affected users within the time the law requires.",
      ],
    },
    {
      heading: "11. Changes",
      blocks: [
        "If this policy changes we tell you in the app and, where needed, ask for your consent again.",
      ],
    },
  ],
};

const termsMn: LegalDoc = {
  title: "Үйлчилгээний нөхцөл",
  description: "LabTrack MN апп-ыг ашиглах нөхцөл ба эмнэлгийн анхааруулга.",
  draft: mnDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "1. Апп юунд зориулагдсан бэ",
      blocks: [
        "LabTrack MN нь шилжүүлэн суулгуулсан хүн өөрийн мэдээллийг цэгцэлж хадгалах, эмийн сануулга тохируулах, хандлагаа харах, эмч болон гэр бүлтэйгээ хуваалцахад зориулагдсан. Аккаунтыг [Компанийн нэр] олгоно; өөрөө бүртгүүлэх боломжгүй.",
      ],
    },
    {
      heading: "2. Эмнэлгийн анхааруулга",
      blocks: [
        [
          "Апп онош тавихгүй, эмчилгээ, эмийн тун санал болгохгүй, эмийн харилцан үйлчлэл шалгахгүй; AI зөвхөн баримтаас утга уншина. Эмчийн зөвлөгөөг орлохгүй.",
          "Эмээ (тариа, наалт ч мөн) эмчийнхээ хамгийн сүүлийн зааврын дагуу хэрэглэнэ үү. Апп дахь бичлэг заавартай зөрвөл эмчийн заавар давамгайлах бөгөөд бичлэгээ шинэчилнэ үү.",
          "Сануулга утасны тохиргоо, батерей хэмнэлт, сүлжээнээс шалтгаалан хоцорч эсвэл ирэхгүй байж болох тул цорын ганц сануулга болгон найдахгүй байхыг зөвлөж байна. Хоцорч ирсэн сануулгаар тунгаа давхар уухгүйн тулд эхлээд апп дахь тэмдэглэлээ шалгана уу; эргэлзвэл эмчдээ хандана уу.",
          "Асран хамгаалагчийн мэдэгдэл болон «критик байж болзошгүй» анхааруулга хоцорч эсвэл ирэхгүй байж болно. Мэдэгдэл ирээгүй нь тун уусан, эсвэл хариу хэвийн гэсэн үг биш. Лаб, эмчийн мэдэгдлийг орлохгүй.",
          "Шинжилгээний хариуны дэргэдэх тэмдэг (↑ өндөр / ↓ бага) нь утгыг лабын хуудсанд хэвлэсэн, эсвэл таны/эмчийн оруулсан хязгаартай харьцуулсан тэмдэг — үнэлгээ, онош биш. Хязгаар байхгүй бол тэмдэг гарахгүй; тэмдэггүй нь «хэвийн» гэсэн үг биш. AI-ын уншсан утгыг эх баримттай тулгаж батална уу.",
          "Яаралтай тусламжийн карт зөвхөн таны бүртгэснийг харуулна; хуучирсан эсвэл одоогийн жортой зөрж болно. Цусны бүлгийг цус сэлбэхийн өмнө лабораториор баталгаажуулна.",
          "Апп яаралтай тусламжийн үйлчилгээг орлохгүй. Яаралтай үед 103 руу залгана уу.",
        ],
      ],
    },
    {
      heading: "3. Таны үүрэг",
      blocks: [
        [
          "Нэвтрэх мэдээллээ бусдад өгөхгүй байж, утсаа түгжээтэй байлгана уу.",
          "Зөвхөн өөрийн, эсвэл өөрийн асран хамгаалдаг хүүхдийн мэдээллийг оруулна уу.",
          "Хуваалцах линк, PIN-ийг зөвхөн итгэдэг хүндээ, тусад нь өгнө үү.",
        ],
      ],
    },
    {
      heading: "4. Хариуцлагын хязгаар",
      blocks: [
        "[Хуульч бичнэ: үйлчилгээний тасалдал, хэрэглэгчийн оруулсан мэдээллийн үнэн зөв байдал, хариуцлагын хязгаар.]",
      ],
    },
    {
      heading: "5. Аккаунт зогсоох, устгах",
      blocks: [
        "Та аккаунтаа хүссэн үедээ устгаж болно (доорх «Аккаунт устгах» холбоос). Нөхцөл зөрчсөн, эсвэл аюулгүй байдлын шалтгаанаар компани аккаунтыг түр түгжиж болох бөгөөд энэ тухай танд мэдэгдэнэ.",
      ],
    },
    {
      heading: "6. Нууцлал ба холбоо барих",
      blocks: [
        "Мэдээллийг хэрхэн боловсруулахыг нууцлалын бодлогод тайлбарласан. Асуулт: [имэйл], [утас]. Хэрэглэх хууль: Монгол Улсын хууль.",
      ],
    },
  ],
};

const termsEn: LegalDoc = {
  title: "Terms of use",
  description: "The terms of using the LabTrack MN app, and its medical notice.",
  draft: enDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "1. What the app is for",
      blocks: [
        "LabTrack MN helps transplant recipients keep their records in order, set medicine reminders, see trends and share with their doctors and family. Accounts are issued by [Company name]; you cannot sign yourself up.",
      ],
    },
    {
      heading: "2. Medical notice",
      blocks: [
        [
          "The app does not diagnose, does not suggest treatment or medicine doses and does not check drug interactions; the AI only reads values from documents. It does not replace your doctor's advice.",
          "Use your medicines (injections and patches too) as your doctor last instructed. If a record in the app differs from those instructions, the doctor's instructions prevail — please update the record.",
          "Reminders may be late or not arrive because of phone settings, battery saving or the network, so we advise you not to rely on them as your only reminder. If a reminder arrives late, check the app's record before taking the dose so you do not take it twice; if unsure, ask your doctor.",
          "Caregiver alerts and “possibly critical” alerts may be late or not arrive. No alert does not mean a dose was taken or a result is normal. They do not replace notices from the lab or your doctor.",
          "The marks next to a result (↑ high / ↓ low) compare the value with the range printed by the lab or entered by you or your doctor — not an assessment or a diagnosis. No range means no mark; no mark does not mean normal. Check every value read by AI against the original document before confirming it.",
          "The emergency card shows only what you recorded; it may be out of date or differ from your current prescription. Blood group must be confirmed by a lab before a transfusion.",
          "The app does not replace emergency services. In an emergency call 103.",
        ],
      ],
    },
    {
      heading: "3. Your responsibilities",
      blocks: [
        [
          "Please do not share your sign-in details, and keep your phone locked.",
          "Please enter only your own data, or that of a child in your care.",
          "Please give a share link and its PIN only to people you trust, separately.",
        ],
      ],
    },
    {
      heading: "4. Limitation of liability",
      blocks: [
        "[For the lawyer: service interruptions, accuracy of user-entered data, limits of liability.]",
      ],
    },
    {
      heading: "5. Suspension and deletion",
      blocks: [
        "You can delete your account at any time (the “Delete account” link below). The company may temporarily lock an account for a breach of these terms or for security reasons, and tells you so.",
      ],
    },
    {
      heading: "6. Privacy and contact",
      blocks: [
        "How data is processed is explained in the privacy policy. Questions: [email], [phone]. Governing law: the law of Mongolia.",
      ],
    },
  ],
};

const deletionMn: LegalDoc = {
  title: "Аккаунт ба мэдээллээ устгах",
  description: "LabTrack MN аккаунт ба мэдээллээ хэрхэн устгах, юу хэзээ устах вэ.",
  draft: mnDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "Апп-аас устгах (хамгийн хурдан)",
      blocks: [
        [
          "LabTrack MN апп-ыг нээж нэвтэрнэ.",
          "Тохиргоо (доод хэсэгт) → «Аккаунт устгах».",
          "Нууц үгээ оруулж, дахин баталгаажуулна.",
        ],
        "Та бүх төхөөрөмжөөс шууд гарна. Устгах өдрийг апп харуулна.",
      ],
    },
    {
      heading: "Апп ашиглах боломжгүй бол",
      blocks: [
        "Нууц үгээ мартсан, утсаа алдсан бол тусламжийн утсанд [утас] залгана уу (ажлын өдөр [цаг]).",
        [
          "Бид таны бүртгэлтэй утасны дугаар руу эргэж залгаж, регистрийн дугаараа хэлэхийг хүснэ. Өөр дугаар руу залгахгүй.",
          "Бүртгэлтэй дугаартаа дуудлага авч чадахгүй бол (утас, SIM алдсан) иргэний үнэмлэхтэйгээ [хаяг]-т биечлэн ирнэ үү.",
          "Таниулсны дараа нэг удаагийн идэвхжүүлэх код бүртгэлтэй дугаар руу SMS-ээр, эсвэл биечлэн QR-аар очно. Та шинэ нууц үгээр нэвтэрч апп-аас устгана.",
          "Бид кодыг утсаар хэзээ ч уншиж өгөхгүй, танаас код, нууц үг асуухгүй.",
        ],
        "Энэ хуудаснаас аккаунт байгаа эсэхийг шалгах, устгах хүсэлт илгээх боломжгүй — таны аккаунтыг бусад хүн устгуулахаас хамгаална.",
      ],
    },
    {
      heading: "Юу устах вэ",
      blocks: [
        [
          "Аккаунт, таны үүсгэсэн бүх профайл (хүүхдийнх ч мөн), эрүүл мэндийн бүх бичлэг, эм, тунгийн түүх, шинжилгээний баримт ба хариу, хуваалцах эрх ба линк, мэдэгдэл.",
          "Танд бусдын профайлыг асран хамгаалагч, эмчийн эрхээр харах эрх байсан бол тэр эрх хасагдана.",
        ],
      ],
    },
    {
      heading: "Хэзээ устах вэ, юу үлдэх вэ",
      blocks: [
        "Хүсэлтээс 30 хоногийн дараа системээс бүрмөсөн устна. Энэ хугацаанд санамсаргүй эсвэл дарамтаар хийсэн хүсэлтийг зөвхөн таны хүсэлтээр, хүн таних шалгалтын дараа сэргээж болно.",
        "Нөөц хуулбарт үлдсэн мэдээлэл [N] хоногийн дотор дарагдаж устна. Аюулгүй байдлын бүртгэл (зөвхөн дугаар, утгагүй) [хугацаа] хадгалагдана. Хуваалцсан хүмүүс таны мэдээллийг өмнө нь татаж авсан бол (PDF гэх мэт) тэр хуулбарт бид хүрэхгүй.",
        "Устгахаас өмнө мэдээллээ хадгалах бол апп-аас PDF, JSON, FHIR экспорт авна уу.",
      ],
    },
  ],
};

const deletionEn: LegalDoc = {
  title: "Delete your account and data",
  description: "How to delete your LabTrack MN account and data, and what is deleted when.",
  draft: enDraft,
  updated: UPDATED,
  sections: [
    {
      heading: "In the app (fastest)",
      blocks: [
        [
          "Open the LabTrack MN app and sign in.",
          "Settings (at the bottom) → “Delete account”.",
          "Enter your password and confirm again.",
        ],
        "You are signed out of every device at once. The app shows the date of deletion.",
      ],
    },
    {
      heading: "If you cannot use the app",
      blocks: [
        "If you forgot your password or lost your phone, call the support line at [phone] (working days, [hours]).",
        [
          "We call you back on your registered phone number and ask for your national ID number. We never call another number.",
          "If you cannot take calls on your registered number (lost phone or SIM), come in person with your ID card to [address].",
          "Once identified, a one-time activation code goes to your registered number by SMS, or as a QR code in person. You sign in with a new password and delete the account in the app.",
          "We never read a code to you over the phone and never ask you for a code or password.",
        ],
        "This page cannot check whether an account exists or send a deletion request — that protects your account from being deleted by someone else.",
      ],
    },
    {
      heading: "What is deleted",
      blocks: [
        [
          "The account, every profile you created (including a child's), all health records, medicines, dose history, lab documents and results, sharing access and links, notifications.",
          "If you could see other people's profiles as a caregiver or doctor, that access is removed.",
        ],
      ],
    },
    {
      heading: "When, and what remains",
      blocks: [
        "Everything is erased from the system permanently 30 days after the request. Within that time an accidental or coerced request can be undone only at your request, after an identity check.",
        "Data left in backups is overwritten within [N] days. The security log (identifiers only, no values) is kept for [period]. Copies that people you shared with downloaded earlier (such as a PDF) are beyond our reach.",
        "To keep your data, export the PDF, JSON or FHIR files in the app before deleting.",
      ],
    },
  ],
};

export const LEGAL: Record<LegalPage, Record<LegalLocale, LegalDoc>> = {
  privacy: { mn: privacyMn, en: privacyEn },
  terms: { mn: termsMn, en: termsEn },
  deletion: { mn: deletionMn, en: deletionEn },
};

export const legalLocale = (raw: string | string[] | undefined): LegalLocale =>
  raw === "en" ? "en" : "mn";
