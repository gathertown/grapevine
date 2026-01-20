import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgExclamationTriangle = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M12.25 8.75V12.75M12.25 15.5V15.49M12.5 15.5C12.5 15.6381 12.3881 15.75 12.25 15.75C12.1119 15.75 12 15.6381 12 15.5C12 15.3619 12.1119 15.25 12.25 15.25C12.3881 15.25 12.5 15.3619 12.5 15.5ZM3.04693 16.2276L10.5309 3.64094C11.3061 2.33714 13.1938 2.33714 13.969 3.64093L21.453 16.2276C22.2457 17.5608 21.285 19.2498 19.734 19.2498H4.766C3.21497 19.2498 2.25424 17.5608 3.04693 16.2276Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" /></svg>;
const Memo = memo(SvgExclamationTriangle);
export default Memo;