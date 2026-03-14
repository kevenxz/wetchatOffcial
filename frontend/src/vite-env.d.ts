/** CSS Modules 声明：让 TypeScript 识别 *.module.css 导入。 */
declare module '*.module.css' {
  const classes: Readonly<Record<string, string>>
  export default classes
}
