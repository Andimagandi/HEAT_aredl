#filamentClass.py
#Description:   HEAT filament module
#Engineer:      T Looby
#Date:          20230228
"""
Class for filament tracing.  Used for ELMs and other filamentary structures
"""
import os
import sys
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import scipy.interpolate as interp
from scipy.interpolate import interp1d
import scipy.integrate as integrate
import pandas as pd
import open3d as o3d
import time
import shutil


#HEAT classes
import toolsClass
tools = toolsClass.tools()
import ioClass
IO = ioClass.IO_HEAT()

import logging
log = logging.getLogger(__name__)

class filament:

    def __init__(self, rootDir, dataPath, chmod=0o774, UID=-1, GID=-1):
        """
        rootDir is root location of python modules (where dashGUI.py lives)
        dataPath is the location where we write all output to
        """
        self.rootDir = rootDir
        tools.rootDir = self.rootDir
        self.dataPath = dataPath
        tools.dataPath = self.dataPath
        self.chmod = chmod
        self.GID = GID
        self.UID = UID
        tools.physicsConstants(self)

        return

    def setupNumberFormats(self, tsSigFigs=6, shotSigFigs=6):
        """
        sets up pythonic string number formats for shot and timesteps
        """
        self.tsFmt = "{:."+"{:d}".format(tsSigFigs)+"f}"
        self.shotFmt = "{:0"+"{:d}".format(shotSigFigs)+"d}"
        return

    def readFilamentFile(self, path):
        """
        reads a filament csv input file

        generates a data pd array
        """

        filFile = path + 'filaments.csv'
        self.filData = pd.read_csv(filFile, sep=',', comment='#', skipinitialspace=True)
        print(self.filData.columns)
        print(self.filData.to_dict().keys())
        return

    def setupFilamentTime(self):
        """
        sets up filament timesteps using data from filament file
        """
        try:
            df = self.filData      
            df['N_dt'] = (df['tMax[s]'] - df['tMin[s]']) / df['dt[s]']
            df['N_dt'] = df['N_dt'].round(0)
            df['N_dt'] = df['N_dt'].astype(int)
            df['tNew'] = df.apply( lambda x:  np.linspace(x['tMin[s]'],x['tMax[s]'],x['N_dt']+1), axis=1)
            self.tsFil = df['tNew'].values

        except:
            print("\n\nError setting up filament time.  Check your filament file\n\n")
            log.info("\n\nError setting up filament time.  Check your filament file\n\n")
            sys.exit()
        return

    def allowed_class_vars(self):
        """
        Writes a list of recognized class variables to HEAT object
        Used for error checking input files and for initialization

        Here is a list of variables with description:
        testvar         dummy for testing

        """


        self.allowed_vars = [
                            'testVar',
                            ]
        return

    def setTypes(self):
        """
        Set variable types for the stuff that isnt a string from the input file
        """

        integers = [                  
                    ]

        floats = [
                  'testVar',
                 ]


        for var in integers:
            if (getattr(self, var) is not None) and (~np.isnan(float(getattr(self, var)))):
                try:
                    setattr(self, var, tools.makeInt(getattr(self, var)))
                except:
                    print("Error with input file var "+var+".  Perhaps you have invalid input values?")
                    log.info("Error with input file var "+var+".  Perhaps you have invalid input values?")
        for var in floats:
            if var is not None:
                if (getattr(self, var) is not None) and (~np.isnan(float(getattr(self, var)))):
                    try:
                        setattr(self, var, tools.makeFloat(getattr(self, var)))
                    except:
                        print("Error with input file var "+var+".  Perhaps you have invalid input values?")
                        log.info("Error with input file var "+var+".  Perhaps you have invalid input values?")

        return
    

    def initializeFilament(self, 
                           rCtr: float, 
                           zCtr: float, 
                           phi: float,
                           sigma_b: float, 
                           sigma_r: float, 
                           sigma_p: float, 
                           E0: float, 
                           ep: object):
        """
        initializes a filament object that can be traced in HEAT

        rCtr: r coordinate center of filament [m]
        zCtr: z coordinate center of filament [m]
        phi: toroidal center of filament [radians]
        sigma_b: characteristic width in parallel direction [m]
        sigma_r: characteristic width in radial (psi) direction [m]
        sigma_p: characteristic width in poloidal direction [m]
                   (note that this is NOT the diamagnetic direction exactly)
        E0: total filament energy at t=0 [J]
        ep: an equilParams object

        """

        self.rCtr = rCtr
        self.zCtr = zCtr
        self.phi = phi
        self.sig_b = sigma_b
        self.sig_r = sigma_r
        self.sig_p = sigma_p
        self.E0 = E0
        self.ep = ep
        self.xCtr = rCtr * np.cos(phi)
        self.yCtr = rCtr * np.sin(phi)
        return

    def initializeFilamentFromDict(self, filDict:dict, id:int, ep:object):
        """
        initializes filament from a dictionary (read from csv file in HEAT)

        dictionary is originally a pandas dataframe, so each row in the filament.csv
        HEAT file is a new id # in the dict.  each row can therefore be accessed by:
        filDict['<parameter>'][<row#>]

        ep is equilParams object
        """
        #initialize this filament
        try:
            self.rCtr = filDict['rCtr[m]'][id]
            self.zCtr = filDict['zCtr[m]'][id]
            self.phi = np.radians(filDict['phiCtr[deg]'][id])
            self.xCtr = self.rCtr * np.cos(self.phi)
            self.yCtr = self.rCtr * np.sin(self.phi)
            self.sig_b = filDict['sig_b[m]'][id]
            self.sig_r = filDict['sig_r[m]'][id]
            self.sig_p = filDict['sig_p[m]'][id]
            self.tMin = filDict['tMin[s]'][id]
            self.tMax = filDict['tMax[s]'][id]
            self.N_sig_r = filDict['N_sig_r'][id]
            self.N_sig_p = filDict['N_sig_p'][id]
            self.N_sig_b = filDict['N_sig_b'][id]
            self.N_r = filDict['N_r'][id]
            self.N_p = filDict['N_p'][id]
            self.N_b = filDict['N_b'][id]
            self.N_vS = filDict['N_vS'][id]
            self.dt = filDict['dt[s]'][id]
            self.decay_t = filDict['decay_t[s]'][id]
            self.N_src_t = filDict['N_src_t'][id]
            self.v_r = filDict['v_r[m/s]'][id]
            self.v_t = filDict['v_t[m/s]'][id]
            self.E0 = filDict['E0[J]'][id]
            self.T0 = filDict['T0[eV]'][id]
            self.ep = ep

        except:
            print("\n\nCould not initialize filament.  Check your filament input file!")
            log.info("\n\nCould not initialize filament.  Check your filament input file!")
            sys.exit()

        return

    def filamentCtrBtrace(self, MHD:object, t:float):
        """
        traces magnetic field at filament center

        PFC object used to get paths
        MHD object used for traces
        t used for name of geqdsk for MAFOT
        """
        #calculate field line for filament center
        xyz = np.array([self.xCtr,self.yCtr,self.zCtr])
        dphi = 1.0
        MHD.ittStruct = 360.0 #360 degree trace
        MHD.writeMAFOTpointfile(xyz,self.gridfileStruct)
        MHD.writeControlFile(self.controlfilePath+self.controlfileStruct, t, 0, mode='struct') #0 for both directions
        MHD.getFieldpath(dphi, self.gridfileStruct, self.controlfilePath, self.controlfileStruct, paraview_mask=False, tag=None)
        Btrace = tools.readStructOutput(self.structOutfile) 
        os.remove(self.structOutfile)
        return Btrace

    def findGuidingCenterPaths(self, pts, MHD):
        """
        """
        MHD.ittStruct = 1.0
        #forward trace
        MHD.writeMAFOTpointfile(pts,self.gridfileStruct)
        MHD.writeControlFile(self.controlfilePath+self.controlfileStruct, self.tEQ, 1.0, mode='struct') #0 for both directions
        MHD.getMultipleFieldPaths(1.0, self.gridfileStruct, self.controlfilePath,
                                self.controlfileStruct)

        structData = tools.readStructOutput(self.structOutfile)
        os.remove(self.structOutfile) #clean up
        q1 = structData[0::2,:] #even indexes are first trace point
        q2 = structData[1::2,:] #odd indexes are second trace point
        return q1, q2


    def buildIntersectionMesh(self):
        """
        builds intersection mesh for open3d ray tracing
        """
        Nt = len(self.t1)
        targets = np.hstack([self.t1, self.t2, self.t3]).reshape(Nt*3,3)
        #cast variables to 32bit for C
        vertices = np.array(targets.reshape(Nt*3,3), dtype=np.float32)
        triangles = np.array(np.arange(Nt*3).reshape(Nt,3), dtype=np.uint32)
        #build intersection mesh and tensors for open3d
        self.mesh = o3d.t.geometry.TriangleMesh()
        self.scene = o3d.t.geometry.RaycastingScene()
        self.mesh_id = self.scene.add_triangles(vertices, triangles)
        return



    def traceFilamentParticles(self, MHD):
        """
        Traces filament macro-particles

        Uses Open3D to accelerate the calculation:
        Zhou, Qian-Yi, Jaesik Park, and Vladlen Koltun. "Open3D: A modern
        library for 3D data processing." arXiv preprint arXiv:1801.09847 (2018).
        """
        pts = self.xyzPts.reshape(self.N_b*self.N_r*self.N_p, 3)
        N_pts = len(pts)
        N_ts = int((self.tMax - self.tMin) / self.dt) + 1
        ts = np.linspace(self.tMin, self.tMax, N_ts)

        print('Number of target faces: {:f}'.format(self.Nt))
        log.info('Number of target faces: {:f}'.format(self.Nt))
        print('Number of filament source points: {:f}'.format(N_pts))
        log.info('Number of filament source points: {:f}'.format(N_pts))

        #setup velocities
        self.setupParallelVelocities()
        #initialize trace step matrix
        self.xyzSteps = np.zeros((self.N_vS, N_pts, N_ts, 3))

        #build intersection mesh
        self.buildIntersectionMesh()
        intersectRecord = np.ones((N_pts, self.N_vS))*np.nan
        #hdotn = np.ones((N_pts))*np.nan
        #initialize shadowMask matrix
        shadowMask = np.zeros((N_pts))



        for i in range(self.N_vS):
            #update time counting variables
            tsNext = np.ones((N_pts))*ts[0]
            t_tot = np.zeros((N_pts)) + tsNext
            tIdxNext = np.zeros((N_pts), dtype=int)
            vec = np.zeros((N_pts, 3))
            frac = np.zeros((N_pts))
            use = np.arange(N_pts)

            #save macroparticle coordinates at t0
            self.xyzSteps[i,:,tIdxNext,:] = pts
            tIdxNext += 1
            tsNext = ts[tIdxNext]

            launchPt = pts.copy()
            v_b = self.vSlices[:,i]
    
            #walk along field line, correcting for v_r, looking for intersections,
            #saving coordinates at ts
            while len(use) > 0:
                #calculate guiding center path for one step
                q1, q2 = self.findGuidingCenterPaths(launchPt[use], MHD)
                #correct guiding center path using radial velocity
                d_b = np.linalg.norm((q2-q1), axis=1) #distance along field
                t_b = d_b / v_b[use] #time along field for this step
                t_tot[use] += t_b #cumulative time along field
                d_r = t_b * self.v_r #radial distance

                #generate local radial coordinate transformation
                R = np.sqrt(q2[:,0]**2 + q2[:,1]**2)
                Z = q2[:,2]
                phi = np.arctan2(q2[:,1], q2[:,0])
                rVec = self.fluxSurfNorms(self.ep, R, Z)
                rX, rY, rZ = tools.cyl2xyz(rVec[:,0], rVec[:,2], phi, degrees=False)
                rVecXYZ = np.vstack((rX,rY,rZ)).T
                rMag = np.linalg.norm(rVecXYZ, axis=1)
                rN = rVecXYZ / rMag[:,None]
                
                #magnetic field line trace corrected with radial (psi) velocity component
                q3 = q2 + d_r[:,np.newaxis] * rN
                vec[use] = q3-q1
                frac[use] = (tsNext[use] - t_tot[use] + t_b) / t_b

                if len(use) > 0:
                    launchPt[use] = q3

                #construct rays
                rMag = np.linalg.norm(vec[use], axis=1)
                rNorm = vec[use] / rMag.reshape((-1,1))

                #calculate intersections
                mask = np.ones((len(q3)))
                rays = o3d.core.Tensor([np.hstack([np.float32(q1),np.float32(rNorm)])],dtype=o3d.core.Dtype.Float32)
                hits = self.scene.cast_rays(rays)
                #convert open3d CPU tensors back to numpy
                hitMap = hits['primitive_ids'][0].numpy()
                distMap = hits['t_hit'][0].numpy()

                #escapes occur where we have 32 bits all set: 0xFFFFFFFF = 4294967295 base10
                escapes = np.where(hitMap == 4294967295)[0]
                mask[escapes] = 0.0
                #when distances to target exceed the trace step, we exclude any hits
                tooLong = np.where(distMap > rMag)[0]
                mask[tooLong] = 0.0

                if np.sum(mask)>0:
                    #we found a hit, or multiple
                    idxHit = np.where(mask==1)[0]
                    intersectRecord[use[idxHit], i] = hitMap[idxHit]
                    #hdotn[i] = np.dot(self.intersectNorms[int(intersectRecord[i])],rNorm[idxHit])
                else:
                    #return nan if we didnt hit anything
                    intersectRecord[use, i] = np.nan
                    #hdotn[i] = np.nan




                #particles we need to keep tracing
                test1 = np.where(np.isnan(intersectRecord[use,i]) == True)[0]
                test2 = np.where(t_tot < self.tMax)[0]

                #use = np.where(np.logical_or(test1,test2)==True)[0]
                use = np.intersect1d(test1,test2)

                #For testing
                #print(self.tMax)
                #print(d_b[0])
                #print(t_b[0])
                #print(t_tot)
                #print(d_r[0])
                #print(q1[0])
                #print(q2[0])
                #print(q3[0])
                #print(rN[0])
                #print(d_r.T.shape)
                #print(rN.shape)
                #print(tsNext)
                #print(self.xyzSteps)
                #input()

                #record particle locations for particles that exceeded timestep
                use2 = np.where(t_tot > tsNext)[0] #particles that crossed a timestep
                use3 = np.intersect1d(use,use2) #crossed a timestep and still not crossed tMax, indexed to N_pts
                use4 = np.where(t_tot[use] > tsNext[use])[0] #crossed a timestep and still not crossed tMax, indexed to use
                if len(use3) > 0:
                    self.xyzSteps[i,use3,tIdxNext[use3],:] = q1[use4] + vec[use3]*frac[use3,None]
                    tIdxNext[use3]+=1
                    tsNext[use3] = ts[tIdxNext[use3]]

            #record the final timestep       
            self.xyzSteps[i,:,-1,:] = launchPt + vec*frac[:,None]



                    #intersect_mask = self.intersectTestOpen3D(q1,q2,self.targetPoints,self.targetNorms)
                    #shadowMask[use] = intersect_mask
                    #use = np.where(shadowMask == 0)[0]

        return



    def setupParallelVelocities(self):
        """
        given an array of energies, in self.E, split each array element into N macro-particles, 
        using the energy distribution function

        """
        self.vSlices = np.ones((self.N_b*self.N_r*self.N_p, self.N_vS))*np.nan
        self.energySlices = np.zeros((self.N_b*self.N_r*self.N_p, self.N_vS))
        self.energyIntegrals = np.zeros((self.N_b*self.N_r*self.N_p, self.N_vS))
        self.energyFracs = np.zeros((self.N_b*self.N_r*self.N_p, self.N_vS))
        self.vBounds = np.zeros((self.N_b*self.N_r*self.N_p, self.N_vS+1))

        T_eV = np.ones((self.N_b*self.N_r*self.N_p))*self.T0
        
        for i in range(len(T_eV)):
            B = (self.mass_eV/self.c**2) / (2.0*T_eV[i])
            vThermal = np.sqrt(2.0*T_eV[i]/(self.mass_eV/self.c**2))
            #set upper bound of v*f(v) (note that this cuts off high energy particles)
            vMax = 5 * vThermal
            v = np.linspace(0,vMax,10000).T

            #PDF for 1D v and for speed
            pdf = lambda x: self.gaussian1D(B, x)
            #1D (old and not correct, i think...)
            #v_pdf = 0.5 * self.mass_eV/self.c**2 * v**2 * pdf(v)
            #3D (Stangeby 2.12 or Chen 7.18)
            v_pdf = 4*np.pi * (B/np.pi)**(3.0/2.0) * v**2 * pdf(v)
            #generate the CDF
            v_cdf = np.cumsum(v_pdf[1:])*np.diff(v)
            v_cdf = np.insert(v_cdf, 0, 0)
            #create bspline interpolators for the cdf and cdf inverse
            inverseCDF = interp1d(v_cdf, v, kind='linear')
            forwardCDF = interp1d(v, v_cdf, kind='linear')
            #CDF location of vSlices and bin boundaries
            cdfBounds = np.linspace(0,v_cdf[-1],self.N_vS+1)
            #space bins uniformly, then makes vSlices center of these bins in CDF space
            cdfSlices = np.diff(cdfBounds)/2.0 + cdfBounds[:-1]
            #vSlices are Maxwellian distribution sample locations (@ bin centers)
            self.vSlices[i,:] = inverseCDF(cdfSlices)
            self.vBounds[i,:] = inverseCDF(cdfBounds)

            #f_E = lambda x: x**2 * np.exp(-x / T_eV[i])
            f_E = lambda x: 2*np.sqrt(x/np.pi) * (1.0/T_eV[i])**(3.0/2.0) * np.exp(-x / T_eV[i])
            #energy slices that correspond to velocity slices
            self.energySlices[i,:] = f_E(0.5 * (self.mass_eV/self.c**2) * self.vSlices[i,:]**2)
            #energy integrals
            for j in range(self.N_vS):
                Elo = 0.5 * (self.mass_eV/self.c**2) * self.vBounds[i,j]**2
                Ehi = 0.5 * (self.mass_eV/self.c**2) * self.vBounds[i,j+1]**2
                self.energyIntegrals[i,j] = integrate.quad(f_E, Elo, Ehi)[0]
            energyTotal = self.energyIntegrals[i,:].sum()
            ##for testing
            #if i==0:
            #    print("Integral Test===")
            #    print(energyTotal)
            #    print(integrate.quad(f_E, 0.0, self.vMax[i])[0])
            #energy fractions
            for j in range(self.N_vS):
                self.energyFracs[i,j] = self.energyIntegrals[i,j] / energyTotal




        ##dummy for testing
        #N_pts = self.N_b*self.N_p*self.N_r
        #self.v_b = np.random.random_sample(N_pts) * 100000.0 #random speeds between 0 and 10km/s
        ##self.v_b = np.ones(N_pts) * 1000.0 
        #self.N_vS = 1

        #print(self.vSlices)
        #input()
        return

    def intersectTestOpen3D(self,q1,q2,targets,targetNorms, batchSize=1000):
        """
        checks if any of the lines (field line traces) generated by MAFOT
        struct program intersect any of the target mesh faces.

        Uses Open3D to accelerate the calculation:
        Zhou, Qian-Yi, Jaesik Park, and Vladlen Koltun. "Open3D: A modern
        library for 3D data processing." arXiv preprint arXiv:1801.09847 (2018).
        """
        t0 = time.time()
        N = len(q2)
        Nt = len(targets)
        print('{:d} Source Faces and {:d} Target Faces in PFC object'.format(N,Nt))

        mask = np.ones((N))

        #construct rays
        r = q2-q1
        rMag = np.linalg.norm(r, axis=1)
        rNorm = r / rMag.reshape((-1,1))

        #cast variables to 32bit for C
        vertices = np.array(targets.reshape(Nt*3,3), dtype=np.float32)
        triangles = np.array(np.arange(Nt*3).reshape(Nt,3), dtype=np.uint32)

        #build intersection mesh and tensors for open3d
        mesh = o3d.t.geometry.TriangleMesh()
        scene = o3d.t.geometry.RaycastingScene()
        mesh_id = scene.add_triangles(vertices, triangles)

        #calculate size of potential arrays in RAM
        #availableRAM = psutil.virtual_memory().available #bytes

        #calculate intersections
        rays = o3d.core.Tensor([np.hstack([np.float32(q1),np.float32(rNorm)])],dtype=o3d.core.Dtype.Float32)
        hits = scene.cast_rays(rays)
        #convert open3d CPU tensors back to numpy
        hitMap = hits['primitive_ids'][0].numpy()
        distMap = hits['t_hit'][0].numpy()

        #escapes occur where we have 32 bits all set: 0xFFFFFFFF = 4294967295 base10
        escapes = np.where(hitMap == 4294967295)[0]
        mask[escapes] = 0.0

        #when distances to target exceed the trace step, we exclude any hits
        tooLong = np.where(distMap > rMag)[0]
        mask[tooLong] = 0.0

        print('Found {:f} shadowed faces'.format(np.sum(mask)))
        log.info('Found {:f} shadowed faces'.format(np.sum(mask)))
        print('Time elapsed: {:f}'.format(time.time() - t0))
        log.info('Time elapsed: {:f}'.format(time.time() - t0))

        return mask



    def createSource(self, t:float, Btrace:np.ndarray):
        """
        creates a filament at time t

        t is timestep at which we calculate filament
        so t in gaussian is t-tMin

        Btrace is magnetic field line trace from MAFOT for filament ctr

        """
        self.gridPsiThetaDistAtCtr(self.rCtr, self.zCtr, multR=10.0, multZ = 10.0)
        #discretize filament into macroparticle sources along field line
        self.discretizeFilament(self.N_r,self.N_p,self.N_b, Btrace, self.N_sig_r, self.N_sig_p, self.N_sig_b)
        self.gaussianAtPts(self.ctrPts, self.xyzPts, t-self.tMin, self.v_r)       
        return

    def fluxSurfNorms(self, ep: object, R:np.ndarray, Z:np.ndarray):
        """
        Calculates vectors normal to poloidal flux surfaces at R,Z coordinates

        returns normal vector coordinates in (R, Phi, Z)

        phiNorm is returned as 0
        """       
        if np.isscalar(R):                   
            R = np.array([R])
        if np.isscalar(Z):                   
            Z = np.array([Z])

        Br = ep.BRFunc.ev(R,Z)
        Bz = ep.BZFunc.ev(R,Z)
        Bt = ep.BtFunc.ev(R,Z)
        Bp = np.sqrt(Br**2+Bz**2)

        Bmag = np.sqrt(Bt**2 + Bp**2)


        bt = np.zeros((len(Bt), 3)) #R,t,Z
        bp = np.zeros((len(Bp), 3)) #R,t,Z
    
        #bt[:,1] = Bt / Bmag
        #bp[:,0] = Br / Bmag
        #bp[:,2] = Bz / Bmag

        bt[:,1] = -1.0
        bp[:,0] = Br / Bp
        bp[:,2] = Bz / Bp


        norms = np.cross(bt,bp)


        mag = np.linalg.norm(norms, axis=1)
        r_hat = np.zeros((len(norms), 3))
        r_hat = norms / mag[:, None]

        return r_hat

    def poloidalVectors(self, ep: object, R: np.ndarray ,Z: np.ndarray):
        """
        Calculates vectors tangent to poloidal flux surfaces in RZ plane at R,Z coordinates
        
        returns normal vector coordinates in (R, Phi, Z)

        phiNorm is returned as 0
        """

        if np.isscalar(R):                   
            R = np.array([R])
        if np.isscalar(Z):                   
            Z = np.array([Z])


        Br = ep.BRFunc.ev(R,Z)
        Bz = ep.BZFunc.ev(R,Z)
        Bt = ep.BtFunc.ev(R,Z)
        Bp = np.sqrt(Br**2+Bz**2)

        Bmag = np.sqrt(Bt**2 + Bp**2)

        bp = np.zeros((len(Bp), 3)) #R,phi,Z

        bp[:,0] = Br / Bp
        bp[:,2] = Bz / Bp

        return bp



    def getTraceSection(self, low:float, high:float, trace:np.ndarray):
        """
        returns a section of a trace between low and high
        """
        dist = self.distance(trace)
        idxDist = np.where(np.logical_and(dist >= low, dist <= high))[0]
        return trace[idxDist]
    

    def interpolateTrace(self, traceData:np.ndarray, N:int, addRawData=False):
        """
        given a trace of coordinates, interpolates to N discrete points
        """
        #calculate distance along wall
        dist = self.distance(traceData)
        
        # Resolution we need given the inputs
        resolution = (dist[-1] - dist[0])/float(N)
        print("Resolution: {:f} m".format(resolution))
        # Calculate how many total grid points we need based upon resolution and
        # total distance around curve/wall
        numpoints = int(np.ceil((dist[-1] - dist[0])/resolution))
        # Spline Interpolation (linear) - Make higher resolution wall.
        interpolator = interp.interp1d(dist, traceData, kind='slinear', axis=0)
        alpha = np.linspace(dist[0], dist[-1], numpoints+2)[1:-1]
        #add in raw data points so that we preserve the corners
        if addRawData == True:
            alpha = np.sort(np.hstack([alpha, dist]))
        
        interpolated_points = interpolator(alpha)
        arr, idx = np.unique(interpolated_points, axis=0, return_index=True)
        interpolated_points = arr[np.argsort(idx)]
     
        return interpolated_points, alpha
    

    def distance(self, traceData:np.ndarray):
        """
        Calculate distance along curve/wall (also called S) of ND points:
        """
        distance = np.cumsum(np.sqrt(np.sum(np.diff(traceData,axis=0)**2,axis=1)))
        distance = np.insert(distance, 0, 0)
        return distance




    def gridPsiThetaDistAtCtr(self, rCtr:float, zCtr:float, multR=10.0, multZ = 10.0):
        """
        generates an RZ grid, and then calculates distances [m] on that grid
        in the psi and theta directions from (self.rCtr, self.zCtr)

        these distances can then be used by gaussian

        multR is multiplier to create R width of grid: R width = multR*sigma_r
        multZ is multiplier to create Z height of grid: Z height = multZ*sigma_z
        """
        ep = self.ep
        sigma_r = self.sig_r
        sigma_p = self.sig_p

        #build rectilinear coordinates around the ctr
        r = np.linspace(rCtr - multR*sigma_r, rCtr + multR*sigma_r, 100)
        z = np.linspace(zCtr - multZ*sigma_p, zCtr + multZ*sigma_p, 100)
        R,Z = np.meshgrid(r,z)

        psiCtr, distPsi, thetaCtr, distTheta = self.fluxCoordDistance(rCtr,zCtr,R,Z)

        #set class variables
        self.distPsi = distPsi
        self.distTheta = distTheta
        self.rGrid = r
        self.zGrid = z
        self.psiCtr = psiCtr
        self.thetaCtr = thetaCtr
        self.gridShape = R.shape

        return

    def gaussianAtPts(self, ctrPts: np.ndarray, xyzPts: np.ndarray, t: float, v_r:float):
        """
        calculates a gaussian, centered at ctrPts, evaluated at xyzPts, at time t
        v_r is radial velocity

        saves gaussian values on 3D grid, as well as distances (psi, theta) used to
        evaluate the gaussian        
        """
        ep = self.ep
        sigma_r = self.sig_r
        sigma_p = self.sig_p

        gaussian = np.zeros((xyzPts.shape[:-1]))
        dPsi = np.zeros((xyzPts.shape[:-1]))
        dTheta = np.zeros((xyzPts.shape[:-1]))

        for i,ctr in enumerate(ctrPts):
            rCtr, zCtr, phiCtr = tools.xyz2cyl(ctr[0],ctr[1],ctr[2])
            xyz = xyzPts[i]
            R,Z,phi = tools.xyz2cyl(xyz[:,:,0],xyz[:,:,1],xyz[:,:,2])
            psiCtr, distPsi, thetaCtr, distTheta = self.fluxCoordDistance(rCtr,zCtr,R,Z)

            #2D gaussian
            #g = self.gaussian2D(distPsi,distTheta,self.sig_r,self.sig_p,t,v_r,self.E0)
            #3D gaussian
            g = self.gaussian3D(distPsi,distTheta,self.distB[i],self.sig_r,self.sig_p,self.sig_b,t,v_r)
            #reshape to meshgrid shape
            #gaussian[i,:,:] = g.reshape((len(distPsi), len(distTheta)))
            #dPsi[i,:,:] = distPsi.reshape((len(distPsi), len(distTheta)))
            #dTheta[i,:,:] = distTheta.reshape((len(distPsi), len(distTheta)))
            gaussian[i,:,:] = g
            dPsi[i,:,:] = distPsi
            dTheta[i,:,:] = distTheta

        self.g_pts = gaussian
        self.distPsi = dPsi
        self.distTheta = dTheta
        return


    def fluxCoordDistance(self, r0:float, z0:float, R:np.ndarray, Z:np.ndarray):
        """
        calculates euclidean distance along flux coordinate surfaces (psi and poloidal)
        from rCtr,zCtr on an R,Z grid

        rCtr and zCtr:  coordinate to calculate flux coordinates at / distance from
        R,Z: meshgrid around rCtr,zCtr

        returns psiCtr, distPsi, thetaCtr, distTheta
        """
        ep = self.ep

        #flux coordinates of ctr
        psiCtr = ep.psiFunc(r0, z0)
        thetaCtr = self.thetaFromRZ(ep, r0, z0)

        #==Find radial coordinates
        #Find coordinate transformation at ctr
        psiaxis = ep.g['psiAxis']
        psiedge = ep.g['psiSep']
        deltaPsi = np.abs(psiedge - psiaxis)
        Bp = ep.BpFunc(r0,z0)
        gradPsi = Bp*r0
        xfm = gradPsi / deltaPsi
        #convert distance in psi to euclidean coordinates
        psiRZ = ep.psiFunc.ev(R,Z)
        distPsi = (psiRZ - psiCtr) / xfm #on grid


        #===Find poloidal coordinates
        thetaRZ = self.thetaFromRZ(ep, R.flatten(), Z.flatten())
        #surfR, surfZ = ep.flux_surface(psiCtr, Npts, thetaRZ[sortIdx])
        surfR = ep.g['lcfs'][:,0]
        surfZ = ep.g['lcfs'][:,1]
        thetaSurf = self.thetaFromRZ(ep, surfR, surfZ)
        #calculate distance along flux surface
        surface = np.vstack((surfR, surfZ)).T
        dSurf = self.distance(surface)
        #interpolator that maps theta back to distance along the flux surface
        interpolator = interp.interp1d(thetaSurf, dSurf, kind='slinear', axis=0)
        dCtr = interpolator(thetaCtr)
        distTheta = interpolator(thetaRZ) - dCtr
        distTheta = distTheta.reshape(R.shape) #on grid

        return psiCtr, distPsi, thetaCtr, distTheta

    def gaussian1D(self, B, x):
        """
        returns a 1D gaussian
        """
        g = np.sqrt(B/np.pi) * np.exp(-B*x**2)
        return g


    def filamentGaussian2D(self, t:float, v_r:float, distPsi:np.ndarray, distTheta:np.ndarray):
        """
        calculates gaussian at time t with radial (psi) velocity v_r       
        """
        #calculate gaussian
        g = self.gaussian2D(distPsi,distTheta,self.sig_r,self.sig_p,t,v_r,self.E0)
        #reshape to meshgrid shape
        g.reshape(distPsi.shape) #on grid
        return g
    

    def gaussian2D(self, dx:np.ndarray, dy:np.ndarray , sigX:float ,sigY:float ,t: float, 
                   v_r:float, lambda_t=500e-6):
        """
        calculates gaussian function with two spatial dimensions and 1 time dimension
        """
        #placeholder for now.  decay time of 500us
        if t!=0:
            A=self.E0
        else:
            A = (1 - t/lambda_t)*self.E0

        exp1 = np.exp( -1.0*(dx - t*v_r)**2 / (2*sigX**2) )
        exp2 = np.exp( -1.0*(dy**2) / (2*sigY**2) )
        g = A  * exp1 * exp2
        return g

    def filamentGaussian3D(self, t:float, v_r:float, distPsi:np.ndarray, distTheta:np.ndarray, distB:np.ndarray):
        """
        calculates gaussian at time t with radial (psi) velocity v_r in three dimensions       
        """
        #calculate gaussian
        g = self.gaussian3D(distPsi,distTheta,distB,self.sig_r,self.sig_p,self.sig_b,t,v_r)
        #reshape to meshgrid shape
        g.reshape(distPsi.shape) #on grid
        return g

    def gaussian3D(self, dx:np.ndarray, dy:np.ndarray, dz:np.ndarray, 
                   sigX:float, sigY:float, sigZ:float, 
                   t:float , v_r:float, A=1.0, decay_t=500e-6):
        """
        calculates gaussian function with three spatial dimensions and 1 time dimension

        multiplies gaussian by E0, so that 3D integral equals E0.

        corresponds to advective-diffusive model
        """
        #A = self.E0 / ( (2*np.pi)**(3.0/2.0) * sigX*sigY*sigZ )  
        #A =1.0 / ( (2*np.pi)**(3.0/2.0) * sigX*sigY*sigZ )  
        #exp1 = np.exp( -1.0*(dx - t*v_r)**2 / (2*sigX**2) )
        #exp2 = np.exp( -1.0*(dy**2) / (2*sigY**2) )
        #exp3 = np.exp( -1.0*(dz**2) / (2*sigZ**2) )

        A = self.E0

        B_x = 1.0 / (2*sigX**2)
        B_y = 1.0 / (2*sigY**2)
        B_z = 1.0 / (2*sigZ**2)
        #1D gaussians
        f_x = lambda x: 2.0 * self.gaussian1D(B_x, x)
        f_y = lambda y: 2.0 * self.gaussian1D(B_y, y)
        f_z = lambda z: 2.0 * self.gaussian1D(B_z, z)
        exp1 = f_x(dx - t*v_r)
        exp2 = f_y(dy)
        exp3 = f_z(dz)
        exp4 = np.exp(-t / decay_t)
        g = A * exp1 * exp2 * exp3 # * exp4


#        print("TEST=====!!!") 
#        intX = integrate.quad(f_x, 0, sigX*10)[0]
#        intY = integrate.quad(f_y, 0, sigY*10)[0]
#        intZ = integrate.quad(f_z, 0, sigZ*10)[0]
#        print(self.E0)
#        print(intX)
#        print(intY)
#        print(intZ)
#        print(intX * intY * intZ)
#        input()

        return g


    def thetaFromRZ(self, ep:object, R:np.ndarray, Z:np.ndarray):
        """
        calculates poloidal coordinate, theta, at R,Z given an equilibrium (ep) object

        returns theta
        """
        r_hat = self.fluxSurfNorms(ep, R, Z)
        r_hat = np.delete(r_hat, 1, 1)  # delete second column (phi)
        R_hat = np.array([1.0, 0.0])
        theta = np.arccos(np.dot(r_hat, R_hat))
        zMid = ep.g['ZmAxis']
        idx = np.where(Z < zMid)[0]
        theta[idx] *= -1.0
        return theta


    def discretizeFilament(self, N_r: int, N_p: int, N_b: int, Btrace: np.ndarray, 
                           N_sig_r: int, N_sig_p: int, N_sig_b: int):
        """
        takes user input parameters and builds a filament 
        
        N_r: number of discrete points in radial (psi) direction
        N_p: number of discrete points in poloidal direction
        N_b: number of discrete points along B field line
        N_sig_r : # of self.sig_r widths for points to cover in +/- radial direction
        N_sig_p : # of self.sig_p widths for points to cover in +/- poloidal direction
        N_sig_0 : # of self.sig_0 widths for points to cover in +/- parallel direction
        """
        d_b = self.distance(Btrace)
        #find index of filament center
        ctr = np.array([self.xCtr, self.yCtr, self.zCtr])
        idx = np.argmin(np.sum(np.abs(Btrace-ctr), axis=1))      
        d_b = d_b - d_b[idx]
        use = np.where(np.abs(d_b) < N_sig_b*self.sig_b)[0]

        #calculate center coordinates along field line
        self.ctrPts, alpha = self.interpolateTrace(Btrace[use], N_b, addRawData=False)
        self.distB = alpha - np.max(alpha) / 2.0

        #calculate points in parallel (B) direction
        bMax = N_sig_b * self.sig_b
        b_pts = np.linspace(-bMax, bMax, N_b)

        #calculate points in radial (psi) direction
        rMax = N_sig_r * self.sig_r
        r_pts = np.linspace(-rMax, rMax, N_r+2)[1:-1]

        #calculate points in poloidal direction
        pMax = N_sig_p * self.sig_p
        p_pts = np.linspace(-pMax, pMax, N_p+2)[1:-1]

        #get radial (psi) vectors for each ctrPt
        R = np.sqrt(self.ctrPts[:,0]**2+self.ctrPts[:,1]**2)
        Z = self.ctrPts[:,2]
        phi = np.arctan2(self.ctrPts[:,1], self.ctrPts[:,0])
        rVec = self.fluxSurfNorms(self.ep, R, Z)

        #convert from R,phi,Z to xyz
        rX, rY, rZ = tools.cyl2xyz(rVec[:,0], rVec[:,2], phi, degrees=False)
        rVecXYZ = np.vstack((rX,rY,rZ)).T
        rMag = np.linalg.norm(rVecXYZ, axis=1)
        rN = rVecXYZ / rMag[:,None]

        #get poloidal vectors for each ctrPt
        pVec = self.poloidalVectors(self.ep, R, Z)
        #convert from R,phi,Z to xyz
        pX, pY, pZ = tools.cyl2xyz(pVec[:,0], pVec[:,2], phi, degrees=False)
        pVecXYZ = np.vstack((pX,pY,pZ)).T
        pMag = np.linalg.norm(pVecXYZ, axis=1)
        pN = pVecXYZ / pMag[:,None]


        #create xyz coordinates for each filament source pt
        xyzPts = np.ones((N_b, N_r, N_p,3))*np.nan
        for i in range(N_b):
            for j in range(N_r):
                for k in range(N_p):
                    xyzPts[i,j,k,:] = self.ctrPts[i] + r_pts[j]*rN[i] - p_pts[k]*pN[i]

        self.xyzPts = xyzPts
        self.rN = rN
        self.pN = pN

        return



    def vectorGlyphs(self, ctrs:np.ndarray, vecs:np.ndarray, label:str, path:str, tag:str = None):
        """
        creates a VTP glyph vector for visualization in paraview
        """
        prefix = label
        IO.writeGlyphVTP(ctrs,vecs,label,prefix,path,tag)
        return



    def plotly2DContour(self, x:np.ndarray, y:np.ndarray, z:np.ndarray ,
                        fig:object = None, cs='plasma',zmin=0.0, zmax=1.0, mode='gauss'):
        """
        plots a plotly 2D contour plot 

        z should be in the shape of a np meshgrid whose dimensions match x and y
        """
        if fig == None:
            fig = go.Figure()

        if mode=='psi':
            #plot psi
            fig = go.Figure(data =
                go.Contour(
                    z=z,
                    x=x, # horizontal axis
                    y=y, # vertical axis
                    colorscale=cs,
                    contours_coloring='heatmap',
                    name='psi',
                    showscale=False,
                    ncontours=20,
                    )
             )  
        elif mode=='theta':
            #plot theta
            fig = go.Figure(data =
                go.Contour(
                    z=z,
                    x=x, # horizontal axis
                    y=y, # vertical axis
                    colorscale=cs,
                    contours_coloring='heatmap',
                    name='theta',
                    showscale=False,
                    ncontours=20,
                    )
             )    
        elif mode=='psiDist':
        #plot psiDist
            fig = go.Figure(data =
                go.Contour(
                    z=z,
                    x=y, # horizontal axis
                    y=z, # vertical axis
                    colorscale=cs,
                    contours_coloring='heatmap',
                    name='psiDistance',
                    showscale=False,
                    ncontours=20,
                    )
             )  

        elif mode=='thetaDist':
        #plot thetaDist
            fig = go.Figure(data =
                go.Contour(
                    z=z,
                    x=y, # horizontal axis
                    y=x, # vertical axis
                    colorscale=cs,
                    contours_coloring='heatmap',
                    name='thetaDistance',
                    showscale=False,
                    ncontours=20,
                    )
             )  
        else:
        #plot gaussian
            fig.add_trace(
                go.Contour(
                    z=z,
                    x=x, # horizontal axis
                    y=y, # vertical axis
                    colorscale=cs,
                    contours_coloring='heatmap',
                    name='guassian',
                    showscale=False,
                    ncontours=20,
                    line = dict(width = 0),
                    zmin=zmin,
                    zmax=zmax,
                    )
             )       


        #update the axes
        fig.update_xaxes(range=[min(x), max(x)], title="R[m]")
        fig.update_yaxes(range=[min(y), max(y)], title="Z[m]")
        fig.update_yaxes(scaleanchor = "x",scaleratio = 1,)

        return fig



    def plotlyAddTrace(self, fig:object, trace:np.ndarray, 
                       name:str=None, color:str=None, mode:str=None, markDict:str=None):
        """
        adds a trace to an existing plotly figure

        fig is an existing figure


        trace is rz coordinates of new trace
        """

        if name is None:
            name = 'trace'
        
        if color is None:
            N = len(px.colors.qualitative.Plotly)
            idx = np.random.randint(0,N)
            color = px.colors.qualitative.Plotly[idx]
        
        if mode is None:
            mode="lines"
        
        if mode == "markers" and markDict == None:
            markDict={'symbol':"circle", 'size':16, 'color':'white'}

        fig.add_trace(
            go.Scatter(
                x=trace[:,0],
                y=trace[:,1],
                mode=mode,
                marker=markDict,
                name=name,
                line=dict(
                    color=color
                        ),
                )
                )


        return fig

    def plotlyEQ(self, ep):
        """
        returns a DASH object for use directly in dash app
        """

        psi = ep.g['psiRZ']

        #plot
        levels = sorted(np.append([0.0,0.05,0.1,0.25,0.5,0.75,0.95, 1.0], np.linspace(0.99,psi.max(),15)))
        #psi data
        fig = go.Figure(data =
            go.Contour(
                z=psi,
                x=ep.g['R'], # horizontal axis
                y=ep.g['Z'], # vertical axis
                colorscale='cividis',
                contours_coloring='heatmap',
                name='psi',
                showscale=False,
                ncontours=20,
                )
         )
        #wall in green
        fig.add_trace(
            go.Scatter(
                x=ep.g['wall'][:,0],
                y=ep.g['wall'][:,1],
                mode="markers+lines",
                name="Wall",
                line=dict(
                    color="#19fa1d"
                        ),
                )
                )

        #lcfs from geqdsk
        fig.add_trace(
            go.Scatter(
                x=ep.g['lcfs'][:,0],
                y=ep.g['lcfs'][:,1],
                mode="markers+lines",
                name="Wall",
                line=dict(
                    color="red"
                        ),
                )
                )


        fig.update_layout(
        #    title="{:f} [s]".format(t),
            xaxis_title="R [m]",
            yaxis_title="Z [m]",
            autosize=True,
            #for aspect ratio
            #autosize=False,
            #width=width*1.1,
            #height=height,
            showlegend=False,
            font=dict(
                size=18,
                ),
            margin=dict(
                l=10,
                r=10,
                b=10,
                t=100,
                pad=4
                )
            )

        fig.update_yaxes(scaleanchor = "x",scaleratio = 1,)
        return fig
    
