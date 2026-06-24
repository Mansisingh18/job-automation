from platforms.naukri import NaukriPortal
from platforms.linkedin import LinkedInPortal
from platforms.indeed import IndeedPortal
from platforms.shine import ShinePortal
from platforms.instahyre import InstahyrePortal
from platforms.wellfound import WellfoundPortal
from platforms.cutshort import CutshortPortal

PORTALS = {
    "naukri":    NaukriPortal,
    "linkedin":  LinkedInPortal,
    "indeed":    IndeedPortal,
    "shine":     ShinePortal,
    "instahyre": InstahyrePortal,
    "wellfound": WellfoundPortal,
    "cutshort":  CutshortPortal,
}
